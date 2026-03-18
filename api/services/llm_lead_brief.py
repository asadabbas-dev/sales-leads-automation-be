"""
LLM-based lead brief / meeting prep generation.

Takes lead + latest run result and returns summary, talking points, checklist.
"""

import json
import re

from openai import AsyncOpenAI

from api.config import settings
from api.schemas.brief import LeadBriefResponse


SYSTEM_PROMPT = """You are a sales enablement assistant. Given a lead and their qualification result, produce a brief for an upcoming call.

Output ONLY valid JSON matching this exact schema (no markdown, no extra text):
{
  "summary": "3-5 sentence paragraph summarizing the lead, why they are qualified, and key context.",
  "talking_points": ["Point 1", "Point 2", "Point 3"],
  "checklist": ["Material or action 1", "Material or action 2"]
}

- summary: One short paragraph.
- talking_points: 3-5 bullet-style talking points for the rep to use on the call.
- checklist: 3-5 items the rep should prepare (e.g. "technical architecture", "pricing sheet", "timeline")."""


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


async def generate_lead_brief(
    lead_data: dict,
    result_json: dict | None = None,
) -> LeadBriefResponse:
    """
    Generate a meeting prep brief from lead data and optional AI result.
    """
    client = _build_client()
    user_parts = [f"Lead: {json.dumps(lead_data, default=str)}"]
    if result_json:
        user_parts.append(f"Qualification result: {json.dumps(result_json, default=str)}")
    user_content = "\n\n".join(user_parts)

    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM returned empty response")

    content = _strip_markdown_json(content)
    data = json.loads(content)
    return LeadBriefResponse.model_validate(data)
