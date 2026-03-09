"""
Database models for runs and idempotency.

Schema matches requirements exactly.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, text
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


class IdempotencyKey(Base):
    """Idempotency keys for deduplication."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )