"""
Optional in-memory rate limit for write endpoints (e.g. POST /opportunities, POST analyze).
Enable via RATE_LIMIT_ENABLED=true. Uses client IP as key.
"""

import time
from collections import defaultdict

from fastapi import Request
from starlette.exceptions import HTTPException

from api.config import settings

# (count, window_start_ts) per key
_store: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))


def _get_client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request) -> None:
    """Raise 429 if rate limit exceeded. No-op if rate limiting is disabled."""
    if not settings.rate_limit_enabled:
        return
    key = _get_client_key(request)
    now = time.monotonic()
    count, window_start = _store[key]
    window_sec = settings.rate_limit_window_seconds
    if now - window_start >= window_sec:
        count, window_start = 0, now
    count += 1
    _store[key] = (count, window_start)
    if count > settings.rate_limit_requests:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again later.",
        )
