"""Company profile (ICP) single-row repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import CompanyProfile

PROFILE_ID = 1


async def get_company_profile(session: AsyncSession) -> CompanyProfile | None:
    return await session.scalar(select(CompanyProfile).where(CompanyProfile.id == PROFILE_ID))


async def get_company_profile_dict(session: AsyncSession) -> dict[str, Any] | None:
    row = await get_company_profile(session)
    if not row:
        return None
    return {
        "industry": row.industry,
        "company_size": row.company_size,
        "budget_min": float(row.budget_min) if row.budget_min is not None else None,
        "budget_max": float(row.budget_max) if row.budget_max is not None else None,
        "intent_keywords": list(row.intent_keywords) if row.intent_keywords else [],
        "location": row.location,
    }


async def upsert_company_profile(
    session: AsyncSession,
    *,
    industry: str | None = None,
    company_size: str | None = None,
    budget_min: float | None = None,
    budget_max: float | None = None,
    intent_keywords: list[str] | None = None,
    location: str | None = None,
) -> CompanyProfile:
    stmt = insert(CompanyProfile).values(
        id=PROFILE_ID,
        industry=industry,
        company_size=company_size,
        budget_min=budget_min,
        budget_max=budget_max,
        intent_keywords=intent_keywords or [],
        location=location,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "industry": industry,
            "company_size": company_size,
            "budget_min": budget_min,
            "budget_max": budget_max,
            "intent_keywords": intent_keywords if intent_keywords is not None else [],
            "location": location,
            "updated_at": func.now(),
        },
    )
    await session.execute(stmt)
    row = await session.scalar(select(CompanyProfile).where(CompanyProfile.id == PROFILE_ID))
    return row
