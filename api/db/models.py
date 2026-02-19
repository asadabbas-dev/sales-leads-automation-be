"""
Database models for runs and idempotency.

Schema matches requirements exactly.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


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
    source: Mapped[str] = mapped_column(String(255), nullable=False)
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


class IdempotencyKey(Base):
    """Idempotency keys for deduplication."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )