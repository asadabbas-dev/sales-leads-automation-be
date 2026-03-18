from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.company_profile_repository import get_company_profile_dict
from api.db.models import Lead, Run
from api.services.icp_scoring import compute_icp_score


def _extract_str(payload: dict, keys: tuple[str, ...]) -> Optional[str]:
    for k in keys:
        v = payload.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


async def ensure_lead_from_payload(
    *,
    session: AsyncSession,
    idempotency_key: str,
    payload: dict,
    source: str | None = None,
) -> str:
    """
    Ensure a Lead row exists for the given deterministic idempotency key.
    This must be safe on retries and concurrent requests.
    """
    name = _extract_str(payload, ("name", "full_name", "fullName"))
    email = _extract_str(payload, ("email", "Email", "EMAIL"))
    phone = _extract_str(payload, ("phone", "Phone", "PHONE", "mobile", "tel"))

    stmt = (
        insert(Lead)
        .values(
            idempotency_key=idempotency_key,
            name=name,
            email=email.lower() if email else None,
            phone=phone,
            latest_source=source,
        )
        .on_conflict_do_update(
            index_elements=[Lead.idempotency_key],
            set_={
                # Only fill missing values; don't overwrite populated fields.
                "name": func.coalesce(Lead.name, name),
                "email": func.coalesce(Lead.email, email.lower() if email else None),
                "phone": func.coalesce(Lead.phone, phone),
                "latest_source": func.coalesce(source, Lead.latest_source),
                "updated_at": func.now(),
            },
        )
        .returning(Lead.id)
    )

    lead_id = await session.scalar(stmt)
    return str(lead_id)


async def apply_enrichment_to_lead(
    *,
    session: AsyncSession,
    lead_id: str,
    run: Run,
) -> None:
    """
    Update the Lead snapshot based on a completed successful run.
    Does NOT modify lifecycle status if it was already moved beyond 'new'.
    """
    result = run.result_json or {}
    lead_data = (result.get("lead") or {}) if isinstance(result, dict) else {}

    name = lead_data.get("name") or run.payload_json.get("name")
    email = lead_data.get("email") or run.payload_json.get("email")
    phone = lead_data.get("phone") or run.payload_json.get("phone")
    score = result.get("score") if isinstance(result, dict) else None
    qualified = result.get("qualified") if isinstance(result, dict) else None

    # status auto-update only from baseline 'new'
    desired_status = None
    if qualified is True:
        desired_status = "qualified"
    elif qualified is False:
        desired_status = "unqualified"

    # ICP score from company profile
    profile = await get_company_profile_dict(session)
    payload_flat = {k: v for k, v in (run.payload_json or {}).items() if v is not None}
    icp_score = (
        compute_icp_score(lead_data=payload_flat, result_json=run.result_json, profile=profile)
        if profile
        else None
    )

    await session.execute(
        update(Lead)
        .where(Lead.id == lead_id)
        .values(
            name=func.coalesce(Lead.name, name),
            email=func.coalesce(Lead.email, (str(email).lower() if email else None)),
            phone=func.coalesce(Lead.phone, (str(phone) if phone else None)),
            latest_run_id=str(run.id),
            latest_score=score,
            latest_qualified=qualified,
            latest_source=run.source,
            status=case_update_status(desired_status),
            icp_score=icp_score,
            updated_at=func.now(),
        )
    )


def case_update_status(desired_status: str | None):
    """
    Return SQLAlchemy expression that only updates status when current status is 'new'.
    """
    if not desired_status:
        return Lead.status
    return func.coalesce(
        func.nullif(Lead.status, "new"),
        desired_status,
    )


async def get_lead_by_id(session: AsyncSession, lead_id: str) -> Lead | None:
    return await session.scalar(select(Lead).where(Lead.id == lead_id))


async def list_leads(
    session: AsyncSession,
    *,
    status: str | None = None,
    source: str | None = None,
    owner: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Lead]:
    stmt = select(Lead).order_by(Lead.updated_at.desc()).limit(limit).offset(offset)
    if status:
        stmt = stmt.where(Lead.status == status)
    if source:
        stmt = stmt.where(Lead.latest_source.ilike(f"%{source}%"))
    if owner:
        stmt = stmt.where(Lead.owner.ilike(f"%{owner}%"))
    if search:
        stmt = stmt.where(
            or_(
                Lead.name.ilike(f"%{search}%"),
                Lead.email.ilike(f"%{search}%"),
                Lead.phone.ilike(f"%{search}%"),
            )
        )
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def count_leads(
    session: AsyncSession,
    *,
    status: str | None = None,
    source: str | None = None,
    owner: str | None = None,
    search: str | None = None,
) -> int:
    stmt = select(func.count()).select_from(Lead)
    if status:
        stmt = stmt.where(Lead.status == status)
    if source:
        stmt = stmt.where(Lead.latest_source.ilike(f"%{source}%"))
    if owner:
        stmt = stmt.where(Lead.owner.ilike(f"%{owner}%"))
    if search:
        stmt = stmt.where(
            or_(
                Lead.name.ilike(f"%{search}%"),
                Lead.email.ilike(f"%{search}%"),
                Lead.phone.ilike(f"%{search}%"),
            )
        )
    return int((await session.scalar(stmt)) or 0)


async def update_lead(
    session: AsyncSession,
    *,
    lead_id: str,
    status: str | None = None,
    owner: str | None = None,
    next_action_at: Any | None = None,
    next_action_note: str | None = None,
) -> Lead:
    values: dict[str, Any] = {"updated_at": func.now()}
    if status is not None:
        values["status"] = status
    if owner is not None:
        values["owner"] = owner
    if next_action_at is not None:
        values["next_action_at"] = next_action_at
    if next_action_note is not None:
        values["next_action_note"] = next_action_note

    await session.execute(update(Lead).where(Lead.id == lead_id).values(**values))
    row = await session.scalar(select(Lead).where(Lead.id == lead_id))
    return row


async def list_runs_for_lead(
    session: AsyncSession,
    *,
    lead_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[Run]:
    stmt = (
        select(Run)
        .where(Run.lead_id == lead_id)
        .order_by(Run.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = await session.execute(stmt)
    return list(rows.scalars().all())

