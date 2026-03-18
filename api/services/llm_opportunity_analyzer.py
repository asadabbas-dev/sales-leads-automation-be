"""
LLM-based opportunity analysis: industry match, complexity, success probability, etc.
Structured output; retry on transient failures (up to 3 times).
"""

import json
import logging
import re

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from api.config import settings

logger = logging.getLogger(__name__)

# Configurable retry count for transient failures
ANALYZER_RETRY_COUNT = 3


class OpportunityAnalysisOutput(BaseModel):
    """Structured output from the opportunity analyzer."""

    industry_match: list[str] = Field(default_factory=list, description="Industries that match this opportunity")
    proposal_complexity: str = Field(..., description="e.g. low, medium, high")
    estimated_success_probability: float = Field(..., ge=0.0, le=1.0)
    recommended_company_size: str | None = Field(None, description="e.g. small, mid-size, enterprise")
    key_requirements: list[str] = Field(default_factory=list, description="Key requirements for the opportunity")


SYSTEM_PROMPT = """You are an opportunity analyst. Given a grant or funding opportunity, analyze it and output ONLY valid JSON (no markdown, no extra text) with this exact structure:
{
  "industry_match": ["industry1", "industry2"],
  "proposal_complexity": "low" | "medium" | "high",
  "estimated_success_probability": 0.0 to 1.0,
  "recommended_company_size": "small" | "mid-size" | "enterprise" or null,
  "key_requirements": ["requirement1", "requirement2"]
}
Be concise. Use industry_match and key_requirements as arrays of strings."""


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


async def analyze_opportunity_with_llm(
    title: str,
    description: str | None = None,
    organization: str | None = None,
    deadline: str | None = None,
    funding_value: float | None = None,
    industry_tags: list[str] | None = None,
    location: str | None = None,
) -> OpportunityAnalysisOutput:
    """
    Call LLM to analyze an opportunity. Returns structured analysis.
    Raises on validation error; caller should retry on transient errors.
    """
    parts = [f"Title: {title}"]
    if description:
        parts.append(f"Description: {description}")
    if organization:
        parts.append(f"Organization: {organization}")
    if deadline:
        parts.append(f"Deadline: {deadline}")
    if funding_value is not None:
        parts.append(f"Funding value: {funding_value}")
    if industry_tags:
        parts.append(f"Industry tags: {', '.join(industry_tags)}")
    if location:
        parts.append(f"Location: {location}")
    user_content = "\n\n".join(parts)

    client = _build_client()
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM returned empty response")

    content = _strip_markdown_json(content)
    data = json.loads(content)
    return OpportunityAnalysisOutput.model_validate(data)


async def analyze_opportunity_with_retry(
    title: str,
    description: str | None = None,
    organization: str | None = None,
    deadline: str | None = None,
    funding_value: float | None = None,
    industry_tags: list[str] | None = None,
    location: str | None = None,
    max_retries: int = ANALYZER_RETRY_COUNT,
) -> OpportunityAnalysisOutput | None:
    """
    Run analyzer with retries. Returns analysis or None on persistent failure.
    Logs failures.
    """
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            return await analyze_opportunity_with_llm(
                title=title,
                description=description,
                organization=organization,
                deadline=deadline,
                funding_value=funding_value,
                industry_tags=industry_tags or [],
                location=location,
            )
        except Exception as e:
            last_error = e
            logger.warning(
                "Opportunity analyzer attempt %s/%s failed: %s",
                attempt + 1,
                max_retries,
                e,
                exc_info=True,
            )
    logger.error(
        "Opportunity analyzer failed after %s attempts: %s",
        max_retries,
        last_error,
    )
    return None
