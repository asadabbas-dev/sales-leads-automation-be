"""
LLM-based lead classification and structured extraction.

Strict schema enforcement — fail loudly on mismatch.
"""

import json
import re

from openai import AsyncOpenAI

from api.config import settings
from api.schemas.enrich import EnrichLeadResponse


SYSTEM_PROMPT = """You are a lead qualification system. Analyze the raw lead payload and:
1. Classify lead quality (qualified: true/false)
2. Assign a score 0-100
3. List 1-5 reasons for the qualification decision
4. Extract structured fields: name, email, phone, budget (number), intent, urgency (low|medium|high), industry

Output ONLY valid JSON matching this exact schema (no markdown, no extra text):
{
  "qualified": true,
  "score": 82,
  "reasons": ["High budget", "Urgent intent"],
  "lead": {
    "name": "string or null",
    "email": "string or null",
    "phone": "string or null",
    "budget": 5000,
    "intent": "string or null",
    "urgency": "low",
    "industry": "string or null"
  }
}"""


def _build_client() -> AsyncOpenAI:
    """Build the AsyncOpenAI client, optionally with a custom base URL."""
    kwargs: dict = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return AsyncOpenAI(**kwargs)


async def enrich_lead_with_llm(payload: dict) -> EnrichLeadResponse:
    """
    Call LLM to classify and extract structured lead data.
    Returns a strict EnrichLeadResponse — raises on schema mismatch.
    """
    client = _build_client()
    user_content = json.dumps(payload, default=str)

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

    # Strict Pydantic validation — raises ValidationError on mismatch
    return EnrichLeadResponse.model_validate(data)


def _strip_markdown_json(text: str) -> str:
    """Remove ```json ... ``` wrapper if present."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text