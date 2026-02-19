from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from api.db.models import IdempotencyKey, Run


# ======================================================
# IDEMPOTENCY HELPERS
# ======================================================

async def get_existing_run_by_key(
    session: AsyncSession, idempotency_key: str
) -> Run | None:
    """Return the most recent successful run for this idempotency key."""
    stmt = (
        select(Run)
        .where(Run.idempotency_key == idempotency_key, Run.status == "success")
        .order_by(Run.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def try_create_idempotency_key(session: AsyncSession, key: str) -> bool:
    """
    Atomically insert idempotency key.
    Returns True if created, False if key already exists (race condition).
    """
    try:
        session.add(IdempotencyKey(key=key))
        await session.flush()
        return True
    except IntegrityError:
        await session.rollback()
        return False


async def delete_idempotency_key(session: AsyncSession, key: str) -> None:
    """Delete an idempotency key (after failure, so retries can reprocess)."""
    await session.execute(delete(IdempotencyKey).where(IdempotencyKey.key == key))
    await session.flush()


# ======================================================
# RUN CRUD OPERATIONS
# ======================================================

async def list_runs(
    session: AsyncSession,
    status: str | None = None,
    source: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Run]:
    stmt = select(Run).order_by(Run.created_at.desc()).limit(limit).offset(offset)
    if status:
        stmt = stmt.where(Run.status == status)
    if source:
        stmt = stmt.where(Run.source.ilike(f"%{source}%"))
    if search:
        from sqlalchemy import or_, cast, String
        stmt = stmt.where(
            or_(
                Run.source.ilike(f"%{search}%"),
                cast(Run.id, String).ilike(f"%{search}%"),
                Run.error.ilike(f"%{search}%"),
            )
        )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_run_by_id(session: AsyncSession, run_id: str) -> Run | None:
    stmt = select(Run).where(Run.id == run_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def count_runs(
    session: AsyncSession,
    status: str | None = None,
    source: str | None = None,
    search: str | None = None,
) -> int:
    stmt = select(func.count()).select_from(Run)
    if status:
        stmt = stmt.where(Run.status == status)
    if source:
        stmt = stmt.where(Run.source.ilike(f"%{source}%"))
    if search:
        from sqlalchemy import or_, cast, String
        stmt = stmt.where(
            or_(
                Run.source.ilike(f"%{search}%"),
                cast(Run.id, String).ilike(f"%{search}%"),
                Run.error.ilike(f"%{search}%"),
            )
        )
    result = await session.execute(stmt)
    return result.scalar() or 0


async def create_run(
    session: AsyncSession,
    source: str,
    payload_json: dict,
    result_json: dict | None,
    status: str,
    priority: str | None = None,
    scheduled_at: str | None = None,
    error: str | None = None,
    idempotency_key: str | None = None,
) -> Run:
    """Create a run record for audit trail."""
    run = Run(
        source=source,
        payload_json=payload_json,
        result_json=result_json,
        status=status,
        priority=priority,
        scheduled_at=scheduled_at,
        error=error,
        idempotency_key=idempotency_key,
    )
    session.add(run)
    await session.flush()
    return run


async def update_run(
    session: AsyncSession,
    run_id: str,
    *,
    status: str | None = None,
    result_json: dict | None = None,
    error: str | None = None,
) -> Run:
    values = {}
    if status is not None:
        values["status"] = status
    if result_json is not None:
        values["result_json"] = result_json
    if error is not None:
        values["error"] = error

    if not values:
        raise ValueError("No fields to update")

    stmt = (
        update(Run)
        .where(Run.id == run_id)
        .values(**values)
        .execution_options(synchronize_session="fetch")
    )
    await session.execute(stmt)
    await session.flush()
    result = await session.execute(select(Run).where(Run.id == run_id))
    return result.scalar_one()


async def delete_run(session: AsyncSession, run_id: str) -> None:
    """Hard delete run (admin/system only)."""
    await session.execute(delete(Run).where(Run.id == run_id))
    await session.flush()