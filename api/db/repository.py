"""
Repository layer for runs and idempotency.

Ensures no duplicate processing and full audit trail.
"""

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import IdempotencyKey, Run


async def get_existing_run_by_key(
    session: AsyncSession, idempotency_key: str
) -> Run | None:
    """Return the most recent successful run for this idempotency key."""
    stmt = (
        select(Run)
        .where(
            Run.idempotency_key == idempotency_key,
            Run.status == "success",
        )
        .order_by(Run.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def try_create_idempotency_key(session: AsyncSession, key: str) -> bool:
    """
    Atomically insert idempotency key.
    Returns True if created, False if key already exists (retry/race).
    """
    try:
        session.add(IdempotencyKey(key=key))
        await session.flush()
        return True
    except IntegrityError:
        await session.rollback()
        return False


async def delete_idempotency_key(session: AsyncSession, key: str) -> None:
    """Remove idempotency key (e.g. on processing failure to allow retry)."""
    await session.execute(delete(IdempotencyKey).where(IdempotencyKey.key == key))


async def list_runs(
    session: AsyncSession,
    status: str | None = None,
    qualified: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Run]:
    """List runs with optional filters."""
    stmt = select(Run).order_by(Run.created_at.desc()).limit(limit).offset(offset)
    if status:
        stmt = stmt.where(Run.status == status)
    if qualified is not None:
        qual_val = "true" if qualified else "false"
        stmt = stmt.where(
            Run.result_json.isnot(None),
            Run.result_json["qualified"].astext == qual_val,
        )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_run_by_id(session: AsyncSession, run_id: str) -> Run | None:
    """Get a single run by ID."""
    stmt = select(Run).where(Run.id == run_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def count_runs(
    session: AsyncSession,
    status: str | None = None,
    qualified: bool | None = None,
) -> int:
    """Count runs with optional filters."""
    from sqlalchemy import func

    stmt = select(func.count()).select_from(Run)
    if status:
        stmt = stmt.where(Run.status == status)
    if qualified is not None:
        qual_val = "true" if qualified else "false"
        stmt = stmt.where(
            Run.result_json.isnot(None),
            Run.result_json["qualified"].astext == qual_val,
        )
    result = await session.execute(stmt)
    return result.scalar() or 0


async def create_run(
    session: AsyncSession,
    source: str,
    payload_json: dict,
    result_json: dict | None,
    status: str,
    error: str | None = None,
    idempotency_key: str | None = None,
) -> Run:
    """Create a run record for audit."""
    run = Run(
        source=source,
        payload_json=payload_json,
        result_json=result_json,
        status=status,
        error=error,
        idempotency_key=idempotency_key,
    )
    session.add(run)
    await session.flush()
    return run
