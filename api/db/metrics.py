from __future__ import annotations

from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import Lead, Run


async def get_runs_summary(session: AsyncSession) -> dict[str, Any]:
    total = await session.scalar(select(func.count()).select_from(Run)) or 0

    by_status = await session.execute(
        select(Run.status, func.count()).group_by(Run.status)
    )
    status_counts = {status: count for status, count in by_status.all()}

    success = int(status_counts.get("success", 0))
    failed = int(status_counts.get("failed", 0))
    pending = int(status_counts.get("pending", 0))

    qualified_count = await session.scalar(
        select(func.count())
        .select_from(Run)
        .where(
            Run.status == "success",
            Run.result_json.isnot(None),
            Run.result_json["qualified"].astext == "true",
        )
    )
    qualified = int(qualified_count or 0)

    # Avg processing time based on DB timestamps (completed_at - created_at)
    avg_ms = await session.scalar(
        select(
            func.avg(
                func.extract("epoch", (Run.completed_at - Run.created_at)) * 1000.0
            )
        ).where(Run.completed_at.isnot(None))
    )

    today_calls = await session.scalar(
        select(func.count())
        .select_from(Run)
        .where(func.date(Run.created_at) == func.current_date())
    )

    return {
        "total": int(total),
        "success": success,
        "failed": failed,
        "pending": pending,
        "qualified": qualified,
        "avg_processing_ms": int(avg_ms) if avg_ms is not None else None,
        "ai_calls_today": int(today_calls or 0),
    }


async def get_source_breakdown(session: AsyncSession) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(
            Run.source,
            func.count().label("total"),
            func.sum(case((Run.status == "success", 1), else_=0)).label("success"),
            func.sum(case((Run.status == "failed", 1), else_=0)).label("failed"),
            func.sum(
                case(
                    (
                        (Run.status == "success")
                        & (Run.result_json.isnot(None))
                        & (Run.result_json["qualified"].astext == "true"),
                        1,
                    ),
                    else_=0,
                )
            ).label("qualified"),
        )
        .group_by(Run.source)
        .order_by(func.count().desc())
    )

    result: list[dict[str, Any]] = []
    for source, total, success, failed, qualified in rows.all():
        total_i = int(total or 0)
        qualified_i = int(qualified or 0)
        result.append(
            {
                "source": source,
                "total": total_i,
                "success": int(success or 0),
                "failed": int(failed or 0),
                "qualified": qualified_i,
                "qualified_rate": (qualified_i / total_i) if total_i else 0.0,
            }
        )
    return result


async def get_leads_funnel(session: AsyncSession) -> dict[str, int]:
    rows = await session.execute(select(Lead.status, func.count()).group_by(Lead.status))
    counts = {status: int(count or 0) for status, count in rows.all()}

    total = await session.scalar(select(func.count()).select_from(Lead)) or 0

    return {
        "total": int(total),
        "new": int(counts.get("new", 0)),
        "contacted": int(counts.get("contacted", 0)),
        "qualified": int(counts.get("qualified", 0)),
        "unqualified": int(counts.get("unqualified", 0)),
        "lost": int(counts.get("lost", 0)),
    }

