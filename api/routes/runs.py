"""
/runs — CRUD + list endpoints for automation run history.

Flow:
  POST /runs  →  saves run as "pending"
              →  calls /enrich-lead internally (AI qualification)
              →  updates run to "success" or "failed" with result_json
              →  returns the completed run
"""

from typing import Optional
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
from api.services.llm_enrichment import enrich_lead_with_llm

router = APIRouter(prefix="/runs", tags=["runs"])


# ============================================================
# Pydantic schemas
# ============================================================

class RunCreateRequest(BaseModel):
    source: str = Field(..., examples=["manual", "api", "ui", "webhook"])
    workflow: str = Field(..., examples=["b2b", "b2c"])
    priority: Optional[str] = Field(None, examples=["low", "medium", "high"])
    scheduled_at: Optional[str] = Field(None, examples=["2026-02-18T10:30:00Z"])
    # payload_json = the raw lead data the AI will process
    payload_json: dict = Field(
        ...,
        description="Raw lead data (name, email, phone, budget, intent, urgency, industry, etc.)",
        examples=[{"name": "John Smith", "email": "john@acme.com", "phone": "+1234567890", "budget": 50000, "intent": "Looking for enterprise plan", "urgency": "high", "industry": "SaaS"}],
    )


class RunUpdateRequest(BaseModel):
    status: Optional[str] = Field(None, examples=["success", "failed", "pending"])
    result_json: Optional[dict] = None
    error: Optional[str] = None


class RunResponse(BaseModel):
    id: str
    source: str
    status: str
    workflow: Optional[str] = None
    priority: Optional[str]
    scheduled_at: Optional[str]
    payload_json: dict
    result_json: Optional[dict]
    error: Optional[str]
    idempotency_key: Optional[str]
    created_at: str
    # Flattened from result_json for frontend convenience
    qualified: Optional[bool]
    score: Optional[int]

    @classmethod
    def from_run(cls, run) -> "RunResponse":
        result = run.result_json or {}
        return cls(
            id=str(run.id),
            source=run.source,
            status=run.status,
            workflow=getattr(run, "workflow", None),
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
    qualified: Optional[bool]
    score: Optional[int]
    result_json: Optional[dict]
    error: Optional[str]
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
    status: Optional[str] = Query(None, description="Filter: success | failed | pending"),
    source: Optional[str] = Query(None, description="Filter by source (partial match)"),
    search: Optional[str] = Query(None, description="Search run ID, source, or error"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Return paginated, optionally filtered list of runs."""
    async with async_session() as session:
        runs = await list_runs(session, status=status, source=source, search=search, limit=limit, offset=offset)
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
    """
    Create a run and immediately process it through AI qualification.

    Flow:
      1. Save run as status="pending" with the raw payload
      2. Call OpenAI to qualify the lead (score, qualified, reasons, extracted fields)
      3. Update run to status="success" + result_json  (or "failed" + error)
      4. Return the completed run
    """

    # ── Step 1: Save pending run ──────────────────────────────────────────────
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
        await session.commit()
        run_id = str(run.id)
        created_at = run.created_at.isoformat() if run.created_at else ""

    # ── Step 2: Run AI enrichment ─────────────────────────────────────────────
    try:
        result = await enrich_lead_with_llm(data.payload_json)
        result_dict = result.model_dump()
        final_status = "success"
        error_msg = None
    except Exception as e:
        result_dict = None
        final_status = "failed"
        error_msg = str(e)

    # ── Step 3: Update run with AI result ─────────────────────────────────────
    async with async_session() as session:
        updated = await update_run(
            session=session,
            run_id=run_id,
            status=final_status,
            result_json=result_dict,
            error=error_msg,
        )
        await session.commit()

    # ── Step 4: Return ────────────────────────────────────────────────────────
    qualified = result_dict.get("qualified") if result_dict else None
    score = result_dict.get("score") if result_dict else None

    return RunCreateResponse(
        id=run_id,
        status=final_status,
        qualified=qualified,
        score=score,
        result_json=result_dict,
        error=error_msg,
        created_at=created_at,
    )


# ============================================================
# UPDATE RUN  PUT /runs/{run_id}
# ============================================================

@router.put("/{run_id}")
async def update_run_api(run_id: str, data: RunUpdateRequest):
    """Manually update status, result, or error on a run."""
    _validate_uuid(run_id)

    if not any([data.status, data.result_json, data.error]):
        raise HTTPException(
            status_code=400,
            detail="Provide at least one field: status, result_json, or error.",
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
    """Hard-delete a run record."""
    _validate_uuid(run_id)

    async with async_session() as session:
        run = await get_run_by_id(session, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found.")

        await delete_run(session, run_id)
        await session.commit()

    return {"success": True, "deleted": run_id}