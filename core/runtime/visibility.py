from __future__ import annotations

from typing import Any

_ALWAYS_SHOWING = {"showing": True}


def annotate_owner_visibility(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """Annotate messages as visible unless they already carry display metadata."""
    for msg in messages:
        msg.setdefault("display", _ALWAYS_SHOWING)
    return messages, "owner"
