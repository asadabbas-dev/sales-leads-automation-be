from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import AiAnalysis, CrmRecord, Lead, Opportunity, OpportunityScore, Run

HIGH_SCORE_THRESHOLD = 80


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


async def get_automation_health(session: AsyncSession) -> dict[str, Any]:
    """Last run time, failed count in last 24h, and recent error entries."""
    last_run = await session.scalar(
        select(func.max(Run.created_at)).select_from(Run)
    )
    last_run_at = last_run.isoformat() if last_run else None

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    failed_24h = await session.scalar(
        select(func.count())
        .select_from(Run)
        .where(Run.status == "failed", Run.created_at >= cutoff)
    )
    failed_last_24h = int(failed_24h or 0)

    recent_errors_rows = await session.execute(
        select(Run.id, Run.created_at, Run.error)
        .where(Run.error.isnot(None), Run.error != "")
        .order_by(Run.created_at.desc())
        .limit(5)
    )
    recent_errors = []
    for run_id, at, err in recent_errors_rows.all():
        msg = (err or "")[:200]
        if len(err or "") > 200:
            msg += "..."
        recent_errors.append(
            {
                "run_id": str(run_id),
                "at": at.isoformat() if at else None,
                "message": msg,
            }
        )

    return {
        "last_run_at": last_run_at,
        "failed_last_24h": failed_last_24h,
        "recent_errors": recent_errors,
    }


async def get_high_value_overview(session: AsyncSession) -> dict[str, int]:
    """High-score leads (>=80), qualified this week, new this week."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    high_score_leads = await session.scalar(
        select(func.count())
        .select_from(Lead)
        .where(Lead.latest_score >= HIGH_SCORE_THRESHOLD)
    )

    qualified_this_week = await session.scalar(
        select(func.count())
        .select_from(Lead)
        .where(Lead.status == "qualified", Lead.updated_at >= week_ago)
    )

    new_this_week = await session.scalar(
        select(func.count())
        .select_from(Lead)
        .where(Lead.created_at >= week_ago)
    )

    high_icp_count = await session.scalar(
        select(func.count())
        .select_from(Lead)
        .where(Lead.icp_score >= HIGH_SCORE_THRESHOLD)
    )

    return {
        "high_score_leads": int(high_score_leads or 0),
        "qualified_this_week": int(qualified_this_week or 0),
        "new_this_week": int(new_this_week or 0),
        "high_icp_count": int(high_icp_count or 0),
    }


OPPORTUNITY_HIGH_SCORE_THRESHOLD = 80


async def get_opportunities_overview(session: AsyncSession) -> dict[str, Any]:
    """Total opportunities, count with at least one ai_analysis, count with score >= 80."""
    total = await session.scalar(select(func.count()).select_from(Opportunity)) or 0
    analyzed = await session.scalar(
        select(func.count(func.distinct(AiAnalysis.opportunity_id))).select_from(
            AiAnalysis
        )
    ) or 0
    high_score = await session.scalar(
        select(func.count(func.distinct(OpportunityScore.opportunity_id))).select_from(
            OpportunityScore
        ).where(OpportunityScore.score >= OPPORTUNITY_HIGH_SCORE_THRESHOLD)
    ) or 0
    return {
        "total_opportunities": int(total),
        "analyzed_count": int(analyzed),
        "high_score_count": int(high_score),
    }


async def get_opportunities_pipeline_counts(session: AsyncSession) -> dict[str, int]:
    """Count of opportunities per CRM stage."""
    rows = await session.execute(
        select(CrmRecord.stage, func.count()).group_by(CrmRecord.stage)
    )
    return {stage: int(count) for stage, count in rows.all()}

