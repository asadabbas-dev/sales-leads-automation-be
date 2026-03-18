"""
LLM-based proposal brief generator: summary, eligibility reasoning, outline, checklist.
Generate on demand; retry once on transient failure.
"""

import json
import logging
import re

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, field_validator

from api.config import settings

logger = logging.getLogger(__name__)

PROPOSAL_BRIEF_RETRIES = 2  # initial + 1 retry


def _ensure_string(value: str | list) -> str:
    """Accept string or list (LLM sometimes returns outline as list); normalize to string."""
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if item)
    return str(value) if value is not None else ""


class ProposalBriefOutput(BaseModel):
    """Structured proposal brief from the LLM."""

    summary: str = Field(..., description="Brief summary of the opportunity")
    eligibility_reasoning: str = Field(..., description="Why we may be eligible (or not)")
    proposal_outline: str = Field(..., description="Suggested structure/sections for the proposal")
    checklist: list[str] = Field(default_factory=list, description="Required materials or steps")

    @field_validator("proposal_outline", mode="before")
    @classmethod
    def normalize_proposal_outline(cls, v: str | list) -> str:
        return _ensure_string(v)

    @field_validator("summary", "eligibility_reasoning", mode="before")
    @classmethod
    def normalize_string_fields(cls, v: str | list) -> str:
        return _ensure_string(v)


SYSTEM_PROMPT = """You are a proposal writer. Given a funding/grant opportunity (and optional prior analysis), produce a proposal brief. Output ONLY valid JSON (no markdown, no extra text):
{
  "summary": "2-4 sentence summary of the opportunity",
  "eligibility_reasoning": "Why our organization may or may not be eligible",
  "proposal_outline": "A single string describing suggested sections or structure (e.g. numbered or bullet text), NOT an array",
  "checklist": ["item1", "item2", "..." ]
}
Be concise. proposal_outline must be a string. checklist is an array of required materials or action items."""


def _build_client() -> AsyncOpenAI:
    kwargs: dict = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return AsyncOpenAI(**kwargs)


def _strip_markdown_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text


async def generate_proposal_brief_llm(
    opportunity: dict,
    ai_analysis: dict | None = None,
) -> ProposalBriefOutput:
    """
    Call LLM to generate proposal brief from opportunity and optional ai_analysis.
    Raises on parse/validation error; caller should retry on transient errors.
    """
    parts = [
        f"Title: {opportunity.get('title', '')}",
        f"Description: {opportunity.get('description') or 'No description'}",
    ]
    if opportunity.get("organization"):
        parts.append(f"Organization: {opportunity['organization']}")
    if opportunity.get("deadline"):
        parts.append(f"Deadline: {opportunity['deadline']}")
    if opportunity.get("funding_value") is not None:
        parts.append(f"Funding: {opportunity['funding_value']}")
    if opportunity.get("industry_tags"):
        parts.append(f"Industry tags: {', '.join(opportunity['industry_tags'])}")
    if opportunity.get("location"):
        parts.append(f"Location: {opportunity['location']}")
    if ai_analysis:
        parts.append("\nPrior analysis:")
        parts.append(f"  Key requirements: {ai_analysis.get('key_requirements') or []}")
        parts.append(f"  Proposal complexity: {ai_analysis.get('proposal_complexity')}")
        parts.append(f"  Success probability: {ai_analysis.get('success_probability')}")
    user_content = "\n".join(parts)

    client = _build_client()
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM returned empty response")

    content = _strip_markdown_json(content)
    data = json.loads(content)
    return ProposalBriefOutput.model_validate(data)


async def generate_proposal_brief_with_retry(
    opportunity: dict,
    ai_analysis: dict | None = None,
    max_retries: int = PROPOSAL_BRIEF_RETRIES,
) -> ProposalBriefOutput | None:
    """Generate proposal brief with retries. Returns None on persistent failure."""
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            return await generate_proposal_brief_llm(
                opportunity=opportunity,
                ai_analysis=ai_analysis,
            )
        except Exception as e:
            last_error = e
            logger.warning(
                "Proposal brief attempt %s/%s failed: %s",
                attempt + 1,
                max_retries,
                e,
                exc_info=True,
            )
    logger.error(
        "Proposal brief failed after %s attempts: %s",
        max_retries,
        last_error,
    )
    return None
