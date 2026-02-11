"""
Idempotency key generation.

sha256(email + phone) - normalized for consistent hashing.
"""

import hashlib


def compute_idempotency_key(payload: dict) -> str:
    """
    Generate idempotency key from lead payload.

    Uses sha256(email + phone). Extracts email/phone from common field names
    (case-insensitive). Empty/missing values normalized to empty string.
    """
    email = _extract_string(payload, ["email", "Email", "EMAIL"])
    phone = _extract_string(payload, ["phone", "Phone", "PHONE", "mobile", "tel"])

    combined = f"{email}{phone}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def _extract_string(payload: dict, keys: list[str]) -> str:
    """Extract first matching key value as string."""
    for key in keys:
        if key in payload and payload[key] is not None:
            val = payload[key]
            return str(val).strip() if isinstance(val, str) else str(val)
    return ""
