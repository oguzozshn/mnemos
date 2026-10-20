"""Timestamp normalization."""

from __future__ import annotations

from datetime import datetime, timezone


def to_utc_iso(value: str | float | int | None) -> str | None:
    """Normalize an ISO string or a Unix timestamp to `YYYY-MM-DDTHH:MM:SSZ` (UTC)."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
    else:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
