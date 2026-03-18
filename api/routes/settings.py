"""Settings endpoints (e.g. ICP / company profile)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.db.company_profile_repository import (
    get_company_profile_dict,
    upsert_company_profile,
)
from api.db.session import async_session
from api.schemas.common import success_response

router = APIRouter(prefix="/settings", tags=["settings"])


class IcpConfigResponse(BaseModel):
    industry: Optional[str] = None
    company_size: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    intent_keywords: list[str] = Field(default_factory=list)
    location: Optional[str] = None


class IcpConfigUpdate(BaseModel):
    industry: Optional[str] = None
    company_size: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    intent_keywords: Optional[list[str]] = None
    location: Optional[str] = None


@router.get("/icp")
async def get_icp_config():
    async with async_session() as session:
        data = await get_company_profile_dict(session)
        await session.commit()
    resp = IcpConfigResponse() if not data else IcpConfigResponse(**data)
    return success_response(data=resp.model_dump(), message="ICP config retrieved successfully.")


@router.put("/icp")
async def update_icp_config(body: IcpConfigUpdate):
    async with async_session() as session:
        await upsert_company_profile(
            session,
            industry=body.industry,
            company_size=body.company_size,
            budget_min=body.budget_min,
            budget_max=body.budget_max,
            intent_keywords=body.intent_keywords,
            location=body.location,
        )
        await session.commit()
        data = await get_company_profile_dict(session)
        await session.commit()
    if not data:
        raise HTTPException(status_code=500, detail="Failed to read ICP config after update")
    return success_response(
        data=IcpConfigResponse(**data).model_dump(),
        message="ICP config updated successfully.",
    )
