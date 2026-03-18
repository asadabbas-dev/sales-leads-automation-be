"""
ICP (Ideal Customer Profile) scoring.

Weights: industry 40%, budget 20%, intent 20%, company_size 20%.
Returns 0-100.
"""


def _normalize(s: str | None) -> str:
    if s is None:
        return ""
    return str(s).strip().lower()


def _industry_match(lead_industry: str | None, profile_industry: str | None) -> int:
    """0 or 40."""
    if not profile_industry or not _normalize(profile_industry):
        return 40  # No filter = full points
    li = _normalize(lead_industry or "")
    pi = _normalize(profile_industry)
    if not li:
        return 0
    if pi in li or li in pi:
        return 40
    return 0


def _budget_match(lead_budget: float | None, min_b: float | None, max_b: float | None) -> int:
    """0 or 20."""
    if min_b is None and max_b is None:
        return 20
    if lead_budget is None:
        return 0
    try:
        b = float(lead_budget)
    except (TypeError, ValueError):
        return 0
    if min_b is not None and b < min_b:
        return 0
    if max_b is not None and b > max_b:
        return 0
    return 20


def _intent_match(lead_intent: str | None, keywords: list | None) -> int:
    """0 or 20."""
    if not keywords or not isinstance(keywords, list):
        return 20
    li = _normalize(lead_intent or "")
    if not li:
        return 0
    for kw in keywords:
        if kw and _normalize(str(kw)) in li:
            return 20
    return 0


def _size_match(lead_size: str | None, profile_size: str | None) -> int:
    """0 or 20."""
    if not profile_size or not _normalize(profile_size):
        return 20
    ls = _normalize(lead_size or "")
    ps = _normalize(profile_size)
    if not ls:
        return 0
    if ps in ls or ls in ps:
        return 20
    return 0


def compute_icp_score(
    lead_data: dict,
    result_json: dict | None,
    profile: dict | None,
) -> int:
    """
    Compute 0-100 ICP score for a lead given optional AI result and company profile.
    lead_data: dict with keys like industry, budget, intent (from lead or payload).
    result_json: optional run result with lead: { industry, budget, intent, ... }.
    profile: optional company_profile row as dict (industry, company_size, budget_min, budget_max, intent_keywords).
    """
    if not profile:
        return 0

    lead = (result_json or {}).get("lead") or {}
    industry = lead.get("industry") or lead_data.get("industry")
    budget = lead.get("budget") or lead_data.get("budget")
    intent = lead.get("intent") or lead_data.get("intent")
    company_size = lead.get("company_size") or lead_data.get("company_size")

    total = (
        _industry_match(industry, profile.get("industry"))
        + _budget_match(
            float(budget) if budget is not None else None,
            profile.get("budget_min"),
            profile.get("budget_max"),
        )
        + _intent_match(intent, profile.get("intent_keywords") or [])
        + _size_match(company_size, profile.get("company_size"))
    )
    return min(100, total)
