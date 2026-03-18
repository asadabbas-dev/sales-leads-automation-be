from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.db.metrics import (
    get_automation_health,
    get_high_value_overview,
    get_leads_funnel,
    get_opportunities_overview,
    get_opportunities_pipeline_counts,
    get_runs_summary,
    get_source_breakdown,
)
from api.db.session import async_session
from api.schemas.common import success_response

router = APIRouter(prefix="/metrics", tags=["metrics"])


class RunsSummaryResponse(BaseModel):
    total: int
    success: int
    failed: int
    pending: int
    qualified: int
    avg_processing_ms: Optional[int] = None
    ai_calls_today: int


class SourceBreakdownItem(BaseModel):
    source: str
    total: int
    success: int
    failed: int
    qualified: int
    qualified_rate: float = Field(..., ge=0, le=1)


class SourceBreakdownResponse(BaseModel):
    items: list[SourceBreakdownItem]


class LeadsFunnelResponse(BaseModel):
    total: int
    new: int
    contacted: int
    qualified: int
    unqualified: int
    lost: int


class RecentErrorItem(BaseModel):
    run_id: str
    at: Optional[str] = None
    message: str


class AutomationHealthResponse(BaseModel):
    last_run_at: Optional[str] = None
    failed_last_24h: int
    recent_errors: list[RecentErrorItem]


class HighValueOverviewResponse(BaseModel):
    high_score_leads: int
    qualified_this_week: int
    new_this_week: int
    high_icp_count: int


@router.get("/runs-summary")
async def runs_summary():
    async with async_session() as session:
        data = await get_runs_summary(session)
        await session.commit()
    payload = RunsSummaryResponse(**data) if isinstance(data, dict) else data
    return success_response(
        data=payload.model_dump() if hasattr(payload, "model_dump") else payload,
        message="Runs summary retrieved successfully.",
    )


@router.get("/source-breakdown")
async def source_breakdown():
    async with async_session() as session:
        items = await get_source_breakdown(session)
        await session.commit()
    data = {"items": items}
    return success_response(data=data, message="Source breakdown retrieved successfully.")


@router.get("/leads-funnel")
async def leads_funnel():
    async with async_session() as session:
        data = await get_leads_funnel(session)
        await session.commit()
    payload = LeadsFunnelResponse(**data) if isinstance(data, dict) else data
    return success_response(
        data=payload.model_dump() if hasattr(payload, "model_dump") else payload,
        message="Leads funnel retrieved successfully.",
    )


@router.get("/automation-health")
async def automation_health():
    async with async_session() as session:
        data = await get_automation_health(session)
        await session.commit()
    payload = AutomationHealthResponse(**data) if isinstance(data, dict) else data
    return success_response(
        data=payload.model_dump() if hasattr(payload, "model_dump") else payload,
        message="Automation health retrieved successfully.",
    )


@router.get("/high-value-overview")
async def high_value_overview():
    async with async_session() as session:
        data = await get_high_value_overview(session)
        await session.commit()
    payload = HighValueOverviewResponse(**data) if isinstance(data, dict) else data
    return success_response(
        data=payload.model_dump() if hasattr(payload, "model_dump") else payload,
        message="High-value overview retrieved successfully.",
    )


@router.get("/opportunities-overview")
async def opportunities_overview():
    """Opportunity counts (total, analyzed, high-score) and CRM pipeline counts by stage."""
    async with async_session() as session:
        overview = await get_opportunities_overview(session)
        pipeline = await get_opportunities_pipeline_counts(session)
        await session.commit()
    return success_response(
        data={"opportunities_overview": overview, "pipeline": pipeline},
        message="Opportunities overview retrieved successfully.",
    )

