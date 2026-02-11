"""
GET /runs - List runs with filters
GET /runs/:id - Get run details
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.db.repository import count_runs, get_run_by_id, list_runs
from api.db.session import async_session

router = APIRouter(prefix="/runs", tags=["runs"])


class RunListItem(BaseModel):
    id: str
    source: str
    status: str
    qualified: bool | None
    score: int | None
    created_at: str
    error: str | None


class RunListResponse(BaseModel):
    runs: list[RunListItem]
    total: int


class RunDetailResponse(BaseModel):
    id: str
    source: str
    status: str
    payload_json: dict
    result_json: dict | None
    error: str | None
    created_at: str


def _run_to_item(run) -> RunListItem:
    qualified = None
    score = None
    if run.result_json:
        qualified = run.result_json.get("qualified")
        score = run.result_json.get("score")
    return RunListItem(
        id=str(run.id),
        source=run.source,
        status=run.status,
        qualified=qualified,
        score=score,
        created_at=run.created_at.isoformat() if run.created_at else "",
        error=run.error,
    )


@router.get("", response_model=RunListResponse)
async def get_runs(
    status: str | None = Query(None, description="success | failed"),
    qualified: bool | None = Query(None, description="Filter by qualification"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List automation runs with optional filters."""
    async with async_session() as session:
        runs = await list_runs(
            session, status=status, qualified=qualified, limit=limit, offset=offset
        )
        total = await count_runs(session, status=status, qualified=qualified)
        items = [_run_to_item(r) for r in runs]
        return RunListResponse(runs=items, total=total)


@router.get("/{run_id}", response_model=RunDetailResponse)
async def get_run(run_id: str):
    """Get run details by ID."""
    try:
        UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run ID")

    async with async_session() as session:
        run = await get_run_by_id(session, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return RunDetailResponse(
            id=str(run.id),
            source=run.source,
            status=run.status,
            payload_json=run.payload_json,
            result_json=run.result_json,
            error=run.error,
            created_at=run.created_at.isoformat() if run.created_at else "",
        )
