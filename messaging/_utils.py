"""Shared utilities for the messaging module."""

from __future__ import annotations

from datetime import UTC, datetime


def now_iso() -> str:
    """Current UTC time as ISO 8601 string."""
    return datetime.now(tz=UTC).isoformat()


def ts_to_iso(ts: float) -> str:
    """Unix float timestamp → ISO 8601 string."""
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()
