"""
Strict Pydantic schemas for /enrich-lead.

All responses MUST conform to these schemas. Fail loudly on mismatch.
"""

from typing import Literal

from pydantic import BaseModel, Field


class EnrichedLead(BaseModel):
    """Structured lead fields extracted from the raw payload."""

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    budget: float | None = None
    intent: str | None = None
    urgency: Literal["low", "medium", "high"] | None = None
    industry: str | None = None


class EnrichLeadResponse(BaseModel):
    """Strict output schema for POST /enrich-lead."""

    qualified: bool
    score: int = Field(..., ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
    lead: EnrichedLead