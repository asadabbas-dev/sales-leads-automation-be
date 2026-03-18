"""
Opportunities CRUD and analyze/proposal endpoints.
Validation, dedup, and normalization per application.md Module 2.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from api.db.opportunities_repository import (
    create_ai_analysis,
    create_opportunity,
    create_opportunity_score,
    ensure_crm_record,
    find_duplicate,
    get_opportunity_with_related,
    list_opportunities,
    opportunity_to_dict,
    update_opportunity,
    update_crm_record,
)
from api.db.company_profile_repository import get_company_profile_dict
from api.db.session import async_session
from api.schemas.common import success_response
from api.deps.rate_limit import check_rate_limit
from api.services.llm_opportunity_analyzer import analyze_opportunity_with_retry
from api.services.opportunity_matching import (
    CRM_CREATE_THRESHOLD,
    compute_opportunity_score,
)
from api.services.llm_proposal_brief import generate_proposal_brief_with_retry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/opportunities", tags=["opportunities"])

# --- Validation / normalization helpers ------------------------------------


def normalize_funding_value(value: Any) -> Optional[float]:
    """Parse funding from string like '$200,000' or number."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    s = re.sub(r"[$,\s]", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def normalize_deadline(value: Any) -> Optional[date]:
    """Parse deadline to date."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def normalize_industry_tags(value: Any) -> list[str]:
    """Ensure industry_tags is a list of non-empty strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    return []


# --- Pydantic schemas -------------------------------------------------------


class OpportunityCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    source: str = Field(..., min_length=1, max_length=64)
    deadline: Optional[str] = None
    funding_value: Optional[float | str] = None
    description: Optional[str] = Field(None, max_length=50000)
    url: Optional[str] = Field(None, max_length=2048)
    organization: Optional[str] = Field(None, max_length=512)
    location: Optional[str] = Field(None, max_length=255)
    industry_tags: Optional[list[str] | str] = None

    @field_validator("title", mode="before")
    @classmethod
    def trim_title(cls, v: Any) -> str:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("funding_value", mode="before")
    @classmethod
    def normalize_funding(cls, v: Any) -> Optional[float]:
        return normalize_funding_value(v)


class OpportunityUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=512)
    source: Optional[str] = Field(None, min_length=1, max_length=64)
    deadline: Optional[str] = None
    funding_value: Optional[float | str] = None
    description: Optional[str] = Field(None, max_length=50000)
    url: Optional[str] = Field(None, max_length=2048)
    organization: Optional[str] = Field(None, max_length=512)
    location: Optional[str] = Field(None, max_length=255)
    industry_tags: Optional[list[str] | str] = None
    status: Optional[str] = Field(None, max_length=32)

    @field_validator("funding_value", mode="before")
    @classmethod
    def normalize_funding(cls, v: Any) -> Optional[float]:
        return normalize_funding_value(v)


VALID_CRM_STAGES = frozenset({
    "New Opportunity",
    "Under Review",
    "Proposal Preparation",
    "Submitted",
    "Won",
    "Lost",
})


class CrmUpdate(BaseModel):
    stage: Optional[str] = Field(None, max_length=64)
    assigned_user: Optional[str] = Field(None, max_length=255)

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in VALID_CRM_STAGES:
            raise ValueError(f"stage must be one of: {sorted(VALID_CRM_STAGES)}")
        return v


def _validate_uuid(value: str) -> None:
    try:
        UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format.")


# --- Routes -----------------------------------------------------------------


@router.post("", status_code=201)
async def create_opportunity_api(request: Request, body: OpportunityCreate):
    """Create opportunity. Dedup by url or (title, source); return 409 if duplicate."""
    check_rate_limit(request)
    title = body.title.strip()
    if not title:
        logger.warning("Create opportunity validation failed: title empty")
        raise HTTPException(status_code=400, detail="Title must not be empty.")
    deadline = normalize_deadline(body.deadline)
    funding = body.funding_value if isinstance(body.funding_value, (int, float)) else normalize_funding_value(body.funding_value)
    industry_tags = normalize_industry_tags(body.industry_tags)
    url = body.url.strip() if body.url else None
    source = body.source.strip() or "manual"

    async with async_session() as session:
        duplicate = await find_duplicate(session, url=url, title=title, source=source)
        if duplicate:
            logger.info("Duplicate opportunity: url=%s title=%s source=%s", url, title, source)
            raise HTTPException(
                status_code=409,
                detail="Opportunity already exists.",
            )
        opp = await create_opportunity(
            session,
            title=title,
            source=source,
            deadline=deadline,
            funding_value=funding,
            description=body.description.strip() if body.description else None,
            url=url,
            organization=body.organization.strip() if body.organization else None,
            location=body.location.strip() if body.location else None,
            industry_tags=industry_tags,
        )
        await session.commit()
        return success_response(
            data=opportunity_to_dict(opp),
            message="Opportunity created successfully.",
        )


@router.get("")
async def list_opportunities_api(
    source: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    stage: Optional[str] = Query(None, description="Filter by CRM stage"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List opportunities with optional filters."""
    async with async_session() as session:
        opportunities, total = await list_opportunities(
            session,
            source=source,
            status=status,
            stage=stage,
            limit=limit,
            offset=offset,
        )
        from api.db.models import CrmRecord, OpportunityScore
        from sqlalchemy import select

        items = [opportunity_to_dict(o) for o in opportunities]
        if opportunities:
            ids = [str(o.id) for o in opportunities]
            # Attach latest score and stage to each item
            for o in opportunities:
                sid = str(o.id)
                score_row = await session.scalar(
                    select(OpportunityScore)
                    .where(OpportunityScore.opportunity_id == sid)
                    .order_by(OpportunityScore.created_at.desc())
                    .limit(1)
                )
                crm_row = await session.scalar(
                    select(CrmRecord).where(CrmRecord.opportunity_id == sid)
                )
                d = next(x for x in items if x["id"] == sid)
                d["score"] = score_row.score if score_row else None
                d["priority"] = score_row.priority if score_row else None
                d["stage"] = crm_row.stage if crm_row else None
                d["assigned_user"] = crm_row.assigned_user if crm_row else None
        await session.commit()
        return success_response(
            data={"opportunities": items, "total": total, "limit": limit, "offset": offset},
            message="Opportunities retrieved successfully.",
        )


@router.get("/{opportunity_id}")
async def get_opportunity_api(opportunity_id: str):
    """Get one opportunity with ai_analysis, latest score, and crm_record."""
    _validate_uuid(opportunity_id)
    async with async_session() as session:
        opp, analysis, score_row, crm = await get_opportunity_with_related(
            session, opportunity_id
        )
        if not opp:
            raise HTTPException(status_code=404, detail="Opportunity not found.")
        await session.commit()
        data = opportunity_to_dict(opp)
        data["ai_analysis"] = (
            {
                "id": str(analysis.id),
                "industry_match": analysis.industry_match or [],
                "proposal_complexity": analysis.proposal_complexity,
                "success_probability": analysis.success_probability,
                "recommended_company_size": analysis.recommended_company_size,
                "key_requirements": analysis.key_requirements or [],
                "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
            }
            if analysis
            else None
        )
        data["score"] = score_row.score if score_row else None
        data["priority"] = score_row.priority if score_row else None
        data["crm_record"] = (
            {
                "id": str(crm.id),
                "stage": crm.stage,
                "assigned_user": crm.assigned_user,
                "updated_at": crm.updated_at.isoformat() if crm.updated_at else None,
            }
            if crm
            else None
        )
        return success_response(data=data, message="Opportunity retrieved successfully.")


@router.patch("/{opportunity_id}")
async def update_opportunity_api(opportunity_id: str, body: OpportunityUpdate):
    """Update opportunity. Same validation and dedup (excluding current id)."""
    _validate_uuid(opportunity_id)
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        logger.warning("Update opportunity validation failed: no fields provided")
        raise HTTPException(status_code=400, detail="Provide at least one field to update.")

    title = updates.get("title")
    if title is not None:
        title = str(title).strip()
        if not title:
            logger.warning("Update opportunity validation failed: title empty")
            raise HTTPException(status_code=400, detail="Title must not be empty.")
    deadline = normalize_deadline(updates.get("deadline")) if "deadline" in updates else None
    funding = None
    if "funding_value" in updates:
        funding = normalize_funding_value(updates["funding_value"])
    industry_tags = None
    if "industry_tags" in updates:
        industry_tags = normalize_industry_tags(updates["industry_tags"])
    url = updates.get("url")
    if url is not None and isinstance(url, str):
        url = url.strip() or None
    source = updates.get("source")
    if source is not None:
        source = str(source).strip() or "manual"

    async with async_session() as session:
        opp = await get_opportunity_with_related(session, opportunity_id)[0]
        if not opp:
            raise HTTPException(status_code=404, detail="Opportunity not found.")
        if title is not None or source is not None:
            duplicate = await find_duplicate(
                session,
                url=url if url is not None else opp.url,
                title=title or opp.title,
                source=source or opp.source,
                exclude_id=opportunity_id,
            )
            if duplicate:
                raise HTTPException(status_code=409, detail="Opportunity already exists with that url or title+source.")
        kwargs = {}
        if "title" in updates and title is not None:
            kwargs["title"] = title
        if "source" in updates and source is not None:
            kwargs["source"] = source
        if "deadline" in updates:
            kwargs["deadline"] = deadline
        if "funding_value" in updates:
            kwargs["funding_value"] = funding
        if "description" in updates:
            kwargs["description"] = updates["description"].strip() if isinstance(updates.get("description"), str) else None
        if "url" in updates:
            kwargs["url"] = url
        if "organization" in updates:
            kwargs["organization"] = updates["organization"].strip() if isinstance(updates.get("organization"), str) else None
        if "location" in updates:
            kwargs["location"] = updates["location"].strip() if isinstance(updates.get("location"), str) else None
        if "industry_tags" in updates:
            kwargs["industry_tags"] = industry_tags
        if "status" in updates:
            kwargs["status"] = updates["status"]
        updated = await update_opportunity(session, opportunity_id, **kwargs)
        await session.commit()
        return success_response(
            data=opportunity_to_dict(updated),
            message="Opportunity updated successfully.",
        )


@router.post("/{opportunity_id}/analyze")
async def analyze_opportunity_api(request: Request, opportunity_id: str):
    """Trigger AI analysis; store in ai_analysis; run matching and create/update score and CRM record if score > 70."""
    check_rate_limit(request)
    _validate_uuid(opportunity_id)
    async with async_session() as session:
        opp, existing_analysis, _, _ = await get_opportunity_with_related(
            session, opportunity_id
        )
        if not opp:
            raise HTTPException(status_code=404, detail="Opportunity not found.")

        opp_dict = opportunity_to_dict(opp)
        analysis_result = await analyze_opportunity_with_retry(
            title=opp.title,
            description=opp.description,
            organization=opp.organization,
            deadline=opp.deadline.isoformat() if opp.deadline else None,
            funding_value=float(opp.funding_value) if opp.funding_value is not None else None,
            industry_tags=opp.industry_tags or [],
            location=opp.location,
        )

        if analysis_result is None:
            await create_ai_analysis(
                session,
                opportunity_id,
                raw_response={"error": "Analysis failed after retries"},
            )
            await session.commit()
            raise HTTPException(
                status_code=502,
                detail="AI analysis failed after retries. Please try again later.",
            )

        analysis_row = await create_ai_analysis(
            session,
            opportunity_id,
            industry_match=analysis_result.industry_match,
            proposal_complexity=analysis_result.proposal_complexity,
            success_probability=analysis_result.estimated_success_probability,
            recommended_company_size=analysis_result.recommended_company_size,
            key_requirements=analysis_result.key_requirements,
            raw_response=analysis_result.model_dump(),
        )
        ai_analysis_dict = {
            "industry_match": analysis_row.industry_match or [],
            "proposal_complexity": analysis_row.proposal_complexity,
            "success_probability": analysis_row.success_probability,
            "key_requirements": analysis_row.key_requirements or [],
            "recommended_company_size": analysis_row.recommended_company_size,
        }
        profile = await get_company_profile_dict(session)
        score_value, priority = compute_opportunity_score(
            opp_dict, ai_analysis_dict, profile
        )
        await create_opportunity_score(
            session,
            opportunity_id,
            score=score_value,
            priority=priority,
        )
        if score_value > CRM_CREATE_THRESHOLD:
            await ensure_crm_record(
                session,
                opportunity_id,
                stage="New Opportunity",
                assigned_user=None,
            )
        await session.commit()
        return success_response(
            data={
                "opportunity_id": opportunity_id,
                "ai_analysis": ai_analysis_dict,
                "score": score_value,
                "priority": priority,
            },
            message="Opportunity analyzed successfully.",
        )


@router.get("/{opportunity_id}/proposal-brief")
async def get_proposal_brief_api(opportunity_id: str):
    """Generate proposal brief (summary, eligibility, outline, checklist) on demand. Retry once on failure."""
    _validate_uuid(opportunity_id)
    async with async_session() as session:
        opp, analysis, _, _ = await get_opportunity_with_related(
            session, opportunity_id
        )
        if not opp:
            raise HTTPException(status_code=404, detail="Opportunity not found.")
        opp_dict = opportunity_to_dict(opp)
        ai_dict = None
        if analysis:
            ai_dict = {
                "industry_match": analysis.industry_match or [],
                "proposal_complexity": analysis.proposal_complexity,
                "success_probability": analysis.success_probability,
                "key_requirements": analysis.key_requirements or [],
                "recommended_company_size": analysis.recommended_company_size,
            }
        brief = await generate_proposal_brief_with_retry(
            opportunity=opp_dict,
            ai_analysis=ai_dict,
        )
        if brief is None:
            raise HTTPException(
                status_code=502,
                detail="Proposal brief generation failed. Please try again later.",
            )
        return success_response(
            data={
                "opportunity_id": opportunity_id,
                "summary": brief.summary,
                "eligibility_reasoning": brief.eligibility_reasoning,
                "proposal_outline": brief.proposal_outline,
                "checklist": brief.checklist,
            },
            message="Proposal brief generated successfully.",
        )


@router.patch("/{opportunity_id}/crm")
async def update_opportunity_crm_api(opportunity_id: str, body: CrmUpdate):
    """Update CRM stage and/or assigned_user for an opportunity. Creates CRM record if missing."""
    _validate_uuid(opportunity_id)
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Provide at least one of stage or assigned_user.")
    async with async_session() as session:
        opp = await get_opportunity_with_related(session, opportunity_id)[0]
        if not opp:
            raise HTTPException(status_code=404, detail="Opportunity not found.")
        await ensure_crm_record(session, opportunity_id, stage="New Opportunity", assigned_user=None)
        crm = await update_crm_record(
            session,
            opportunity_id,
            stage=updates.get("stage"),
            assigned_user=updates.get("assigned_user"),
        )
        await session.commit()
        if not crm:
            raise HTTPException(status_code=404, detail="CRM record not found.")
        return success_response(
            data={
                "id": str(crm.id),
                "opportunity_id": opportunity_id,
                "stage": crm.stage,
                "assigned_user": crm.assigned_user,
                "updated_at": crm.updated_at.isoformat() if crm.updated_at else None,
            },
            message="CRM record updated successfully.",
        )
