"""Common API response format for all endpoints."""

from typing import Any, Optional


def success_response(data: Any = None, message: Optional[str] = None) -> dict:
    """Return a standard success envelope: { success, message?, data? }."""
    out = {"success": True}
    if message is not None:
        out["message"] = message
    if data is not None:
        out["data"] = data
    return out


def error_message(detail: Any) -> str:
    """Normalize FastAPI/HTTPException detail to a single string for the client."""
    if detail is None:
        return "An error occurred."
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        parts = []
        for item in detail:
            if isinstance(item, dict):
                loc = item.get("loc", [])
                msg = item.get("msg", str(item))
                parts.append(f"{'.'.join(str(x) for x in loc)}: {msg}")
            else:
                parts.append(str(item))
        return " ".join(parts) if parts else "Validation error."
    return str(detail)
