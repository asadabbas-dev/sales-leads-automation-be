"""
Database models for runs and idempotency.

Schema matches requirements exactly.
"""

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Lead(Base):
    """
    Lead entity (lead-centric view).

    A lead is keyed by the same deterministic idempotency key used for enrichment
    (sha256(email + phone)), when available.
    """

    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Deterministic key when email/phone exists; used for upsert and linking runs.
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # Lead lifecycle status (simple baseline; can expand later)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="new")

    # Ownership/assignment (phase 2+)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Lightweight follow-up scheduling (phase 2+)
    next_action_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    next_action_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Latest enrichment snapshot (denormalized for quick listing)
    latest_run_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    latest_score: Mapped[int | None] = mapped_column(nullable=True)
    latest_qualified: Mapped[bool | None] = mapped_column(nullable=True)
    latest_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    icp_score: Mapped[int | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )


class Run(Base):
    """Run history for full audit trail."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    lead_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("leads.id"),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    workflow: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # pending | success | failed
    priority: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # low | medium | high
    scheduled_at: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # ISO8601 datetime string
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class CompanyProfile(Base):
    """Single-row ideal customer profile (ICP) config."""

    __tablename__ = "company_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, default=1)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    budget_min: Mapped[float | None] = mapped_column(nullable=True)
    budget_max: Mapped[float | None] = mapped_column(nullable=True)
    intent_keywords: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=None)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )


class IdempotencyKey(Base):
    """Idempotency keys for deduplication."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )


class Opportunity(Base):
    """Grant/opportunity from manual entry or API (no scrapers in phase 1)."""

    __tablename__ = "opportunities"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    funding_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True, index=True)
    organization: Mapped[str | None] = mapped_column(String(512), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry_tags: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="new", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )


class AiAnalysis(Base):
    """AI analysis result for an opportunity (one current per opportunity)."""

    __tablename__ = "ai_analysis"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    opportunity_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    industry_match: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=None)
    proposal_complexity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    success_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommended_company_size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    key_requirements: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=None)
    raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )


class OpportunityScore(Base):
    """Matching engine score for an opportunity (latest per opportunity)."""

    __tablename__ = "opportunity_scores"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    opportunity_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )


class CrmRecord(Base):
    """Internal CRM pipeline stage for an opportunity (one row per opportunity)."""

    __tablename__ = "crm_records"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    opportunity_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    assigned_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )