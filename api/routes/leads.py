from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api.db.leads_repository import (
    count_leads,
    get_lead_by_id,
    list_leads,
    list_runs_for_lead,
    update_lead,
)
from api.db.repository import get_run_by_id
from api.db.session import async_session
from api.routes.runs import RunResponse
from api.schemas.brief import LeadBriefResponse
from api.schemas.common import success_response
from api.services.llm_lead_brief import generate_lead_brief

router = APIRouter(prefix="/leads", tags=["leads"])


class LeadResponse(BaseModel):
    id: str
    idempotency_key: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status: str
    owner: Optional[str] = None
    next_action_at: Optional[str] = None
    next_action_note: Optional[str] = None
    latest_run_id: Optional[str] = None
    latest_score: Optional[int] = None
    latest_qualified: Optional[bool] = None
    latest_source: Optional[str] = None
    icp_score: Optional[int] = None
    created_at: str
    updated_at: str

    @classmethod
    def from_lead(cls, lead) -> "LeadResponse":
        return cls(
            id=str(lead.id),
            idempotency_key=lead.idempotency_key,
            name=lead.name,
            email=lead.email,
            phone=lead.phone,
            status=lead.status,
            owner=lead.owner,
            next_action_at=lead.next_action_at.isoformat() if getattr(lead, "next_action_at", None) else None,
            next_action_note=getattr(lead, "next_action_note", None),
            latest_run_id=str(lead.latest_run_id) if lead.latest_run_id else None,
            latest_score=lead.latest_score,
            latest_qualified=lead.latest_qualified,
            latest_source=lead.latest_source,
            icp_score=getattr(lead, "icp_score", None),
            created_at=lead.created_at.isoformat() if lead.created_at else "",
            updated_at=lead.updated_at.isoformat() if lead.updated_at else "",
        )


class LeadListResponse(BaseModel):
    leads: list[LeadResponse]
    total: int
    limit: int
    offset: int


class LeadUpdateRequest(BaseModel):
    status: Optional[str] = Field(None, examples=["new", "qualified", "unqualified", "contacted", "lost"])
    owner: Optional[str] = None
    next_action_at: Optional[datetime] = None
    next_action_note: Optional[str] = None


def _validate_uuid(value: str) -> None:
    try:
        UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format.")


@router.get("")
async def list_leads_api(
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    async with async_session() as session:
        leads = await list_leads(
            session,
            status=status,
            source=source,
            owner=owner,
            search=search,
            limit=limit,
            offset=offset,
        )
        total = await count_leads(
            session, status=status, source=source, owner=owner, search=search
        )
        await session.commit()

    data = LeadListResponse(
        leads=[LeadResponse.from_lead(l) for l in leads],
        total=total,
        limit=limit,
        offset=offset,
    )
    return success_response(data=data.model_dump(), message="Leads fetched successfully.")


@router.get("/{lead_id}")
async def get_lead_api(lead_id: str):
    _validate_uuid(lead_id)
    async with async_session() as session:
        lead = await get_lead_by_id(session, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found.")
        await session.commit()
    data = LeadResponse.from_lead(lead)
    return success_response(data=data.model_dump(), message="Lead retrieved successfully.")


@router.patch("/{lead_id}")
async def update_lead_api(lead_id: str, data: LeadUpdateRequest):
    _validate_uuid(lead_id)
    if (
        data.status is None
        and data.owner is None
        and data.next_action_at is None
        and data.next_action_note is None
    ):
        raise HTTPException(status_code=400, detail="Provide at least one field to update.")

    async with async_session() as session:
        lead = await get_lead_by_id(session, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found.")
        updated = await update_lead(
            session,
            lead_id=lead_id,
            status=data.status,
            owner=data.owner,
            next_action_at=data.next_action_at,
            next_action_note=data.next_action_note,
        )
        await session.commit()
    data = LeadResponse.from_lead(updated)
    return success_response(data=data.model_dump(), message="Lead updated successfully.")


@router.get("/{lead_id}/runs")
async def list_lead_runs_api(
    lead_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    _validate_uuid(lead_id)
    async with async_session() as session:
        runs = await list_runs_for_lead(session, lead_id=lead_id, limit=limit, offset=offset)
        await session.commit()
    data = [RunResponse.from_run(r) for r in runs]
    return success_response(
        data=[r.model_dump() for r in data],
        message="Lead runs retrieved successfully.",
    )


@router.get("/{lead_id}/brief")
async def get_lead_brief_api(lead_id: str):
    """Generate a meeting prep brief for the lead (summary, talking points, checklist)."""
    _validate_uuid(lead_id)
    async with async_session() as session:
        lead = await get_lead_by_id(session, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found.")
        result_json = None
        if lead.latest_run_id:
            run = await get_run_by_id(session, str(lead.latest_run_id))
            if run and run.result_json:
                result_json = run.result_json
        await session.commit()

    lead_data = {
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "status": lead.status,
        "latest_score": lead.latest_score,
        "latest_qualified": lead.latest_qualified,
        "next_action_note": getattr(lead, "next_action_note", None),
    }
    brief = await generate_lead_brief(lead_data=lead_data, result_json=result_json)
    return success_response(
        data=brief.model_dump(),
        message="Lead brief generated successfully.",
    )

