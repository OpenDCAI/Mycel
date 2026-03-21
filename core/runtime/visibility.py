"""Owner visibility — v3: everything is always visible.

v2 had a two-layer context/showing state machine for private context.
v3 removes private context entirely — all messages are shown to the owner.
"""

from __future__ import annotations

from typing import Any

_ALWAYS_SHOWING = {"showing": True}


def compute_visibility(source: str, is_steer: bool, context: str) -> tuple[bool, str]:
    """Always visible. Kept for call-site compatibility during transition."""
    return True, "owner"


def message_visibility(context: str, tool_names: list[str] | None = None) -> dict[str, Any]:
    """Always visible."""
    return _ALWAYS_SHOWING


def tool_event_visibility(context: str, tool_name: str) -> dict[str, Any]:
    """Always visible."""
    return _ALWAYS_SHOWING


def annotate_owner_visibility(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """Annotate every message as visible."""
    for msg in messages:
        msg["display"] = _ALWAYS_SHOWING
    return messages, "owner"
