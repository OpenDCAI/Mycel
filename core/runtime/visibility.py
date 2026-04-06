"""Owner visibility helpers.

v3 default is "visible unless explicitly hidden". Some backend paths still emit
durable hidden owner messages (for example AskUserQuestion answer anchors), so
this layer must preserve an already-declared display contract.
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
    """Annotate messages as visible unless they already carry display metadata."""
    for msg in messages:
        msg.setdefault("display", _ALWAYS_SHOWING)
    return messages, "owner"
