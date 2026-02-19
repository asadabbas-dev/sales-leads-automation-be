"""
/runs — CRUD + list endpoints for automation run history.
"""

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api.db.repository import (
    count_runs,
    create_run,
    delete_run,
    get_run_by_id,
    list_runs,
    update_run,
)
from api.db.session import async_session

router = APIRouter(prefix="/runs", tags=["runs"])


# ============================================================
# Pydantic schemas
# ============================================================

class RunCreateRequest(BaseModel):
    source: str = Field(..., examples=["manual", "api", "ui", "webhook"])
    payload_json: dict = Field(..., description="Lead input payload")
    workflow: str = Field(..., examples=["b2b", "b2c"])
    priority: Optional[str] = Field(None, examples=["low", "medium", "high"])
    scheduled_at: Optional[str] = Field(None, examples=["2026-02-18T10:30:00Z"])


class RunUpdateRequest(BaseModel):
    status: Optional[str] = Field(None, examples=["success", "failed", "pending"])
    result_json: Optional[dict] = None
    error: Optional[str] = None


class RunResponse(BaseModel):
    id: str
    source: str
    status: str
    priority: Optional[str]
    scheduled_at: Optional[str]
    payload_json: dict
    result_json: Optional[dict]
    error: Optional[str]
    idempotency_key: Optional[str]
    created_at: str
    # Convenience fields derived from result_json
    qualified: Optional[bool]
    score: Optional[int]

    @classmethod
    def from_run(cls, run) -> "RunResponse":
        result = run.result_json or {}
        return cls(
            id=str(run.id),
            source=run.source,
            status=run.status,
            priority=run.priority,
            scheduled_at=run.scheduled_at,
            payload_json=run.payload_json,
            result_json=run.result_json,
            error=run.error,
            idempotency_key=run.idempotency_key,
            created_at=run.created_at.isoformat() if run.created_at else "",
            qualified=result.get("qualified"),
            score=result.get("score"),
        )


class RunCreateResponse(BaseModel):
    id: str
    status: str
    created_at: str


class RunListResponse(BaseModel):
    runs: list[RunResponse]
    total: int
    limit: int
    offset: int


# ============================================================
# Helpers
# ============================================================

def _validate_uuid(run_id: str) -> None:
    try:
        UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run ID format.")


# ============================================================
# LIST RUNS  GET /runs
# ============================================================

@router.get("", response_model=RunListResponse)
async def list_runs_api(
    status: Optional[str] = Query(None, description="Filter by status: success | failed | pending"),
    source: Optional[str] = Query(None, description="Filter by source (partial match)"),
    search: Optional[str] = Query(None, description="Search run ID, source, or error text"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
):
    """Return paginated, optionally filtered list of runs."""
    async with async_session() as session:
        runs = await list_runs(
            session,
            status=status,
            source=source,
            search=search,
            limit=limit,
            offset=offset,
        )
        total = await count_runs(session, status=status, source=source, search=search)
        await session.commit()

    return RunListResponse(
        runs=[RunResponse.from_run(r) for r in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


# ============================================================
# GET SINGLE RUN  GET /runs/{run_id}
# ============================================================

@router.get("/{run_id}", response_model=RunResponse)
async def get_run_api(run_id: str):
    """Fetch a single run by UUID."""
    _validate_uuid(run_id)
    async with async_session() as session:
        run = await get_run_by_id(session, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found.")
        await session.commit()
    return RunResponse.from_run(run)


# ============================================================
# CREATE RUN  POST /runs
# ============================================================

@router.post("", response_model=RunCreateResponse, status_code=201)
async def create_run_api(data: RunCreateRequest):
    """Manually create a new automation run record."""
    async with async_session() as session:
        run = await create_run(
            session=session,
            source=data.source,
            payload_json=data.payload_json,
            result_json=None,
            status="pending",
            priority=data.priority,
            scheduled_at=data.scheduled_at,
            error=None,
            idempotency_key=None,
        )
        await session.commit()  # FIX: was missing — data was silently lost on rollback

    return RunCreateResponse(
        id=str(run.id),
        status=run.status,
        created_at=run.created_at.isoformat() if run.created_at else "",
    )


# ============================================================
# UPDATE RUN  PUT /runs/{run_id}
# ============================================================

@router.put("/{run_id}")
async def update_run_api(run_id: str, data: RunUpdateRequest):
    """Update status, result, or error on an existing run."""
    _validate_uuid(run_id)

    if not any([data.status, data.result_json, data.error]):
        raise HTTPException(
            status_code=400,
            detail="Provide at least one field to update: status, result_json, or error.",
        )

    async with async_session() as session:
        run = await get_run_by_id(session, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found.")

        updated = await update_run(
            session=session,
            run_id=run_id,
            status=data.status,
            result_json=data.result_json,
            error=data.error,
        )
        await session.commit()

    return {"success": True, "id": run_id, "status": updated.status}


# ============================================================
# DELETE RUN  DELETE /runs/{run_id}
# ============================================================

@router.delete("/{run_id}", status_code=200)
async def delete_run_api(run_id: str):
    """Hard-delete a run record (admin / system use only)."""
    _validate_uuid(run_id)

    async with async_session() as session:
        run = await get_run_by_id(session, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found.")

        await delete_run(session, run_id)
        await session.commit()

    return {"success": True, "deleted": run_id}