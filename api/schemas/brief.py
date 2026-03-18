"""Pydantic schema for lead brief (meeting prep) output."""

from pydantic import BaseModel, Field


class LeadBriefResponse(BaseModel):
    """Structured output for GET /leads/{id}/brief."""

    summary: str = Field(..., description="3-5 sentence summary of the lead and fit")
    talking_points: list[str] = Field(
        default_factory=list,
        description="3-5 talking points for the call",
    )
    checklist: list[str] = Field(
        default_factory=list,
        description="Short checklist of materials to prepare",
    )
