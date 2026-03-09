from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.db.metrics import (
    get_leads_funnel,
    get_runs_summary,
    get_source_breakdown,
)
from api.db.session import async_session

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


@router.get("/runs-summary", response_model=RunsSummaryResponse)
async def runs_summary():
    async with async_session() as session:
        data = await get_runs_summary(session)
        await session.commit()
    return data


@router.get("/source-breakdown", response_model=SourceBreakdownResponse)
async def source_breakdown():
    async with async_session() as session:
        items = await get_source_breakdown(session)
        await session.commit()
    return {"items": items}


@router.get("/leads-funnel", response_model=LeadsFunnelResponse)
async def leads_funnel():
    async with async_session() as session:
        data = await get_leads_funnel(session)
        await session.commit()
    return data

