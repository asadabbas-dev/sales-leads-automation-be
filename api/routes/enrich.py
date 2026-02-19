"""
POST /enrich-lead — Lead qualification and extraction.

Idempotent, retry-safe, full audit trail.
"""

from fastapi import APIRouter, HTTPException, Request

from api.config import settings
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
    Enrich and qualify a lead from a raw JSON payload.

    - Idempotent: same email+phone combination returns the cached result.
    - Retry-safe: concurrent duplicate requests receive a 409 with Retry-After.
    - Auditable: every run (success or failure) is persisted to the DB.
    - Size-limited: rejects payloads larger than MAX_PAYLOAD_BYTES.
    """
    # ── 0. Size guard ────────────────────────────────────────────────────────
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.max_payload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Payload too large. Maximum size is {settings.max_payload_bytes} bytes.",
        )

    # ── 1. Parse body ────────────────────────────────────────────────────────
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be a JSON object.")

    idempotency_key = compute_idempotency_key(payload)
    source = _extract_source(payload)

    # ── 2. Idempotency check (skip if no key — anonymous lead) ───────────────
    if idempotency_key:
        async with async_session() as session:
            existing_run = await get_existing_run_by_key(session, idempotency_key)
            if existing_run and existing_run.result_json:
                await session.commit()
                return EnrichLeadResponse.model_validate(existing_run.result_json)

            # Atomically claim this request
            created = await try_create_idempotency_key(session, idempotency_key)
            if not created:
                # Lost race — check if the winner already finished
                existing_run = await get_existing_run_by_key(session, idempotency_key)
                if existing_run and existing_run.result_json:
                    await session.commit()
                    return EnrichLeadResponse.model_validate(existing_run.result_json)
                raise HTTPException(
                    status_code=409,
                    detail="Duplicate request in progress. Retry after a few seconds.",
                    headers={"Retry-After": "5"},
                )

            await session.commit()

    # ── 3. LLM enrichment (outside DB transaction — network I/O) ────────────
    try:
        result = await enrich_lead_with_llm(payload)
    except Exception as e:
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
            if idempotency_key:
                # Release the key so the caller can retry
                await delete_idempotency_key(session, idempotency_key)
            await session.commit()
        raise HTTPException(status_code=502, detail=f"Enrichment failed: {e}") from e

    # ── 4. Persist successful run ────────────────────────────────────────────
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


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_source(payload: dict) -> str:
    """Extract originating source label from the payload for the audit trail."""
    for key in ("source", "Source", "SOURCE", "origin", "channel"):
        val = payload.get(key)
        if val:
            return str(val)
    return "unknown"