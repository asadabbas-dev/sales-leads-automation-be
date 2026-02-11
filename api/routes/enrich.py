"""
POST /enrich-lead - Lead qualification and extraction.

Idempotent, retry-safe, full audit trail.
"""

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.repository import (
    create_run,
    delete_idempotency_key,
    get_existing_run_by_key,
    try_create_idempotency_key,
)
from api.db.session import async_session
from api.schemas.enrich import EnrichLeadResponse
from api.services.idempotency import compute_idempotency_key
from api.services.llm_enrichment import enrich_lead_with_llm

router = APIRouter()


@router.post("", response_model=EnrichLeadResponse)
async def enrich_lead(request: Request):
    """
    Enrich and qualify a lead from raw JSON payload.

    - Idempotent: same email+phone returns cached result
    - Retry-safe: no duplicate processing
    - Auditable: all runs logged to DB
    """
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be a JSON object")

    idempotency_key = compute_idempotency_key(payload)
    source = _extract_source(payload)

    async with async_session() as session:
        # 1. Check for existing result (idempotency)
        existing_run = await get_existing_run_by_key(session, idempotency_key)
        if existing_run and existing_run.result_json:
            await session.commit()
            return EnrichLeadResponse.model_validate(existing_run.result_json)

        # 2. Try to claim this request (atomic insert)
        created = await try_create_idempotency_key(session, idempotency_key)
        if not created:
            # Lost race or retry - fetch result (may not exist yet if other request processing)
            existing_run = await get_existing_run_by_key(session, idempotency_key)
            if existing_run and existing_run.result_json:
                await session.commit()
                return EnrichLeadResponse.model_validate(existing_run.result_json)
            # Key exists but no run yet - other request still processing
            raise HTTPException(
                status_code=409,
                detail="Duplicate request in progress. Retry after a few seconds.",
                headers={"Retry-After": "5"},
            )

        await session.commit()

    # 3. Process with LLM (outside transaction - slow)
    try:
        result = await enrich_lead_with_llm(payload)
    except Exception as e:
        # Log failed run and release idempotency key so retries can reprocess
        async with async_session() as session:
            await create_run(
                session=session,
                source=source,
                payload_json=payload,
                result_json=None,
                status="failed",
                error=str(e),
                idempotency_key=idempotency_key,
            )
            await delete_idempotency_key(session, idempotency_key)
            await session.commit()
        raise HTTPException(status_code=502, detail=f"Enrichment failed: {e}") from e

    # 4. Store successful run
    result_dict = result.model_dump()
    async with async_session() as session:
        await create_run(
            session=session,
            source=source,
            payload_json=payload,
            result_json=result_dict,
            status="success",
            error=None,
            idempotency_key=idempotency_key,
        )
        await session.commit()

    return result


def _extract_source(payload: dict) -> str:
    """Extract source from payload for audit."""
    for key in ["source", "Source", "SOURCE", "origin", "channel"]:
        if key in payload and payload[key]:
            return str(payload[key])
    return "unknown"
