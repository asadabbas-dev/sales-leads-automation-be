"""
LLM-based lead classification and structured extraction.

Strict schema enforcement - fail loudly on mismatch.
"""

import json
import re

from openai import AsyncOpenAI

from api.config import settings
from api.schemas.enrich import EnrichedLead, EnrichLeadResponse


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
    "budget": number or null,
    "intent": "string or null",
    "urgency": "low" or "medium" or "high" or null,
    "industry": "string or null"
  }
}"""


async def enrich_lead_with_llm(payload: dict) -> EnrichLeadResponse:
    """
    Call LLM to classify and extract. Returns strict EnrichLeadResponse.
    Raises on schema mismatch.
    """
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )

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

    # Strip markdown code blocks if present
    content = _strip_markdown_json(content)

    data = json.loads(content)

    # Strict validation - Pydantic raises ValidationError on mismatch
    return EnrichLeadResponse.model_validate(data)


def _strip_markdown_json(text: str) -> str:
    """Remove ```json ... ``` wrapper if present."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text


