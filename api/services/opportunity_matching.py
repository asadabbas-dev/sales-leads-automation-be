"""
Opportunity matching engine: score 0-100 from opportunity + ai_analysis vs company profile.
Weights: Industry 40%, Location 20%, Funding size 15%, Proposal complexity 15%, Technology fit 10%.
"""


def _normalize(s: str | None) -> str:
    if s is None:
        return ""
    return str(s).strip().lower()


def _industry_score(
    opportunity_industry_tags: list[str] | None,
    analysis_industry_match: list[str] | None,
    profile_industry: str | None,
) -> int:
    """0-40. Match opportunity industries (tags or AI industry_match) vs profile.industry."""
    if not profile_industry or not _normalize(profile_industry):
        return 40
    combined = []
    if opportunity_industry_tags:
        combined.extend(_normalize(x) for x in opportunity_industry_tags if x)
    if analysis_industry_match:
        combined.extend(_normalize(x) for x in analysis_industry_match if x)
    if not combined:
        return 0
    pi = _normalize(profile_industry)
    for ind in combined:
        if pi in ind or ind in pi:
            return 40
    return 0


def _location_score(opportunity_location: str | None, profile_location: str | None) -> int:
    """0-20."""
    if not profile_location or not _normalize(profile_location):
        return 20
    if not opportunity_location or not _normalize(opportunity_location):
        return 0
    ol = _normalize(opportunity_location)
    pl = _normalize(profile_location)
    if pl in ol or ol in pl:
        return 20
    return 0


def _funding_score(
    opportunity_funding: float | None,
    profile_budget_min: float | None,
    profile_budget_max: float | None,
) -> int:
    """0-15. Funding value within profile budget range, or no range = full points."""
    if profile_budget_min is None and profile_budget_max is None:
        return 15
    if opportunity_funding is None:
        return 0
    try:
        f = float(opportunity_funding)
    except (TypeError, ValueError):
        return 0
    if profile_budget_min is not None and f < profile_budget_min:
        return 0
    if profile_budget_max is not None and f > profile_budget_max:
        return 0
    return 15


def _complexity_score(proposal_complexity: str | None) -> int:
    """0-15. Prefer lower complexity: low=15, medium=10, high=5."""
    if not proposal_complexity:
        return 8  # unknown
    c = _normalize(proposal_complexity)
    if "low" in c:
        return 15
    if "medium" in c or "mid" in c:
        return 10
    if "high" in c:
        return 5
    return 8


def _technology_fit_score(
    key_requirements: list[str] | None,
    description: str | None,
    intent_keywords: list | None,
) -> int:
    """0-10. Overlap between key_requirements/description and intent_keywords."""
    if not intent_keywords or not isinstance(intent_keywords, list):
        return 10
    text_parts = []
    if key_requirements:
        text_parts.extend(_normalize(r) for r in key_requirements if r)
    if description:
        text_parts.append(_normalize(description))
    combined = " ".join(text_parts)
    if not combined:
        return 0
    for kw in intent_keywords:
        if kw and _normalize(str(kw)) in combined:
            return 10
    return 0


# Score >= this value → "High Priority"
PRIORITY_HIGH_THRESHOLD = 80
# Score > this value → ensure CRM record with stage "New Opportunity"
CRM_CREATE_THRESHOLD = 70


def compute_opportunity_score(
    opportunity: dict,
    ai_analysis: dict | None,
    profile: dict | None,
) -> tuple[int, str]:
    """
    Compute 0-100 score and priority label from opportunity, optional ai_analysis, and company profile.
    opportunity: dict with title, funding_value, location, industry_tags, description, ...
    ai_analysis: dict with industry_match, proposal_complexity, key_requirements (or None).
    profile: company profile dict (industry, location, budget_min, budget_max, intent_keywords) or None.
    Returns (score, priority) e.g. (85, "High Priority").
    """
    if not profile:
        return 0, "No profile"

    industry = _industry_score(
        opportunity.get("industry_tags"),
        (ai_analysis or {}).get("industry_match"),
        profile.get("industry"),
    )
    location = _location_score(
        opportunity.get("location"),
        profile.get("location"),
    )
    funding = _funding_score(
        opportunity.get("funding_value"),
        profile.get("budget_min"),
        profile.get("budget_max"),
    )
    complexity = _complexity_score(
        (ai_analysis or {}).get("proposal_complexity"),
    )
    tech = _technology_fit_score(
        (ai_analysis or {}).get("key_requirements"),
        opportunity.get("description"),
        profile.get("intent_keywords") or [],
    )
    score = min(100, industry + location + funding + complexity + tech)
    priority = "High Priority" if score >= PRIORITY_HIGH_THRESHOLD else "Standard"
    return score, priority
