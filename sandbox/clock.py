"""Sandbox runtime time helpers.

Current mainline runtime storage is Supabase-backed and returns timestamptz.
Keep sandbox/session math in one UTC-aware domain instead of mixing naive and aware datetimes.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def parse_runtime_datetime(raw: str | datetime) -> datetime:
    if isinstance(raw, datetime):
        parsed = raw
    else:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
