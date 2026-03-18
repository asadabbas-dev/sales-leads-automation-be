"""Opportunities, ai_analysis, opportunity_scores, crm_records repository."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.db.models import AiAnalysis, CrmRecord, Opportunity, OpportunityScore


async def find_duplicate(
    session: AsyncSession,
    *,
    url: str | None,
    title: str,
    source: str,
    exclude_id: str | None = None,
) -> Opportunity | None:
    """Return existing opportunity if url or (title, source) matches."""
    if url and url.strip():
        q = select(Opportunity).where(Opportunity.url == url.strip())
        if exclude_id:
            q = q.where(Opportunity.id != exclude_id)
        existing = await session.scalar(q)
        if existing:
            return existing
    q = (
        select(Opportunity)
        .where(func.trim(Opportunity.title) == title.strip(), Opportunity.source == source)
    )
    if exclude_id:
        q = q.where(Opportunity.id != exclude_id)
    return await session.scalar(q)


async def list_opportunities(
    session: AsyncSession,
    *,
    source: str | None = None,
    status: str | None = None,
    stage: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Opportunity], int]:
    """List opportunities with optional filters. stage filters via crm_records."""
    base = select(Opportunity)
    count_base = select(func.count()).select_from(Opportunity)

    if source:
        base = base.where(Opportunity.source == source)
        count_base = count_base.where(Opportunity.source == source)
    if status:
        base = base.where(Opportunity.status == status)
        count_base = count_base.where(Opportunity.status == status)
    if stage:
        subq = select(CrmRecord.opportunity_id).where(CrmRecord.stage == stage)
        base = base.where(Opportunity.id.in_(subq))
        count_base = count_base.where(Opportunity.id.in_(subq))

    total = await session.scalar(count_base) or 0
    base = base.order_by(Opportunity.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(base)
    opportunities = list(result.scalars().all())
    return opportunities, int(total)


async def get_opportunity_by_id(session: AsyncSession, opportunity_id: str) -> Opportunity | None:
    return await session.scalar(select(Opportunity).where(Opportunity.id == opportunity_id))


async def get_opportunity_with_related(
    session: AsyncSession, opportunity_id: str
) -> tuple[Opportunity | None, AiAnalysis | None, OpportunityScore | None, CrmRecord | None]:
    """Get opportunity and its latest ai_analysis, latest score, and crm_record."""
    opp = await get_opportunity_by_id(session, opportunity_id)
    if not opp:
        return None, None, None, None
    analysis = await session.scalar(
        select(AiAnalysis)
        .where(AiAnalysis.opportunity_id == opportunity_id)
        .order_by(AiAnalysis.created_at.desc())
        .limit(1)
    )
    score_row = await session.scalar(
        select(OpportunityScore)
        .where(OpportunityScore.opportunity_id == opportunity_id)
        .order_by(OpportunityScore.created_at.desc())
        .limit(1)
    )
    crm = await session.scalar(
        select(CrmRecord).where(CrmRecord.opportunity_id == opportunity_id)
    )
    return opp, analysis, score_row, crm


async def create_opportunity(
    session: AsyncSession,
    *,
    title: str,
    source: str,
    deadline: date | None = None,
    funding_value: float | None = None,
    description: str | None = None,
    url: str | None = None,
    organization: str | None = None,
    location: str | None = None,
    industry_tags: list[str] | None = None,
) -> Opportunity:
    opp = Opportunity(
        title=title,
        source=source,
        deadline=deadline,
        funding_value=Decimal(str(funding_value)) if funding_value is not None else None,
        description=description,
        url=url,
        organization=organization,
        location=location,
        industry_tags=industry_tags or [],
    )
    session.add(opp)
    await session.flush()
    return opp


async def update_opportunity(
    session: AsyncSession,
    opportunity_id: str,
    *,
    title: str | None = None,
    source: str | None = None,
    deadline: date | None = None,
    funding_value: float | None = None,
    description: str | None = None,
    url: str | None = None,
    organization: str | None = None,
    location: str | None = None,
    industry_tags: list[str] | None = None,
    status: str | None = None,
) -> Opportunity | None:
    opp = await get_opportunity_by_id(session, opportunity_id)
    if not opp:
        return None
    if title is not None:
        opp.title = title
    if source is not None:
        opp.source = source
    if deadline is not None:
        opp.deadline = deadline
    if funding_value is not None:
        opp.funding_value = Decimal(str(funding_value))
    if description is not None:
        opp.description = description
    if url is not None:
        opp.url = url
    if organization is not None:
        opp.organization = organization
    if location is not None:
        opp.location = location
    if industry_tags is not None:
        opp.industry_tags = industry_tags
    if status is not None:
        opp.status = status
    return opp


async def create_ai_analysis(
    session: AsyncSession,
    opportunity_id: str,
    *,
    industry_match: list[str] | None = None,
    proposal_complexity: str | None = None,
    success_probability: float | None = None,
    recommended_company_size: str | None = None,
    key_requirements: list[str] | None = None,
    raw_response: dict | None = None,
) -> AiAnalysis:
    row = AiAnalysis(
        opportunity_id=opportunity_id,
        industry_match=industry_match or [],
        proposal_complexity=proposal_complexity,
        success_probability=success_probability,
        recommended_company_size=recommended_company_size,
        key_requirements=key_requirements or [],
        raw_response=raw_response,
    )
    session.add(row)
    await session.flush()
    return row


async def create_opportunity_score(
    session: AsyncSession,
    opportunity_id: str,
    score: int,
    priority: str | None = None,
) -> OpportunityScore:
    row = OpportunityScore(
        opportunity_id=opportunity_id,
        score=score,
        priority=priority,
    )
    session.add(row)
    await session.flush()
    return row


async def ensure_crm_record(
    session: AsyncSession,
    opportunity_id: str,
    stage: str = "New Opportunity",
    assigned_user: str | None = None,
) -> CrmRecord:
    existing = await session.scalar(
        select(CrmRecord).where(CrmRecord.opportunity_id == opportunity_id)
    )
    if existing:
        return existing
    row = CrmRecord(
        opportunity_id=opportunity_id,
        stage=stage,
        assigned_user=assigned_user,
    )
    session.add(row)
    await session.flush()
    return row


async def update_crm_record(
    session: AsyncSession,
    opportunity_id: str,
    *,
    stage: str | None = None,
    assigned_user: str | None = None,
) -> CrmRecord | None:
    row = await session.scalar(
        select(CrmRecord).where(CrmRecord.opportunity_id == opportunity_id)
    )
    if not row:
        return None
    if stage is not None:
        row.stage = stage
    if assigned_user is not None:
        row.assigned_user = assigned_user
    return row


def opportunity_to_dict(opp: Opportunity) -> dict[str, Any]:
    """Serialize opportunity for API response."""
    return {
        "id": str(opp.id),
        "title": opp.title,
        "source": opp.source,
        "deadline": opp.deadline.isoformat() if opp.deadline else None,
        "funding_value": float(opp.funding_value) if opp.funding_value is not None else None,
        "description": opp.description,
        "url": opp.url,
        "organization": opp.organization,
        "location": opp.location,
        "industry_tags": opp.industry_tags or [],
        "status": opp.status,
        "created_at": opp.created_at.isoformat() if opp.created_at else "",
        "updated_at": opp.updated_at.isoformat() if opp.updated_at else "",
    }
