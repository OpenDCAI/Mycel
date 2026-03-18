"""Display projection — pure functions for computing display metadata.

@@@display-projection — two-layer state: latent (internal) + display (metadata).

latent ∈ {"owner", "external"} — tracks whose context we're in. Never leaves backend.
display.showing: bool — render instruction for frontend.

All display computation lives here in core/ so both core/runtime/middleware
and backend/web/services can import the same code. Code exists once.
"""

from __future__ import annotations

from typing import Any

_TELL_OWNER_TOOLS = frozenset({"tell_owner"})


def compute_showing(source: str, is_steer: bool, latent: str) -> tuple[bool, str]:
    """Compute display for a HumanMessage. Returns (showing, new_latent)."""
    if source == "owner":
        return True, "owner"
    if source == "external":
        new_latent = latent if is_steer else "external"
        return False, new_latent
    # system — follow current context
    return latent == "owner", latent


def ai_display(latent: str, tool_call_names: list[str]) -> dict[str, Any]:
    """Compute display metadata for an AIMessage."""
    is_tell = any(n in _TELL_OWNER_TOOLS for n in tool_call_names)
    return {"showing": latent == "owner", "is_tell_owner": is_tell}


def tool_display(latent: str, tool_name: str) -> dict[str, Any]:
    """Compute display metadata for a ToolMessage."""
    is_tell = tool_name in _TELL_OWNER_TOOLS
    return {"showing": latent == "owner", "is_tell_owner": is_tell}


def tool_call_display(latent: str, tool_call_name: str) -> dict[str, Any]:
    """Compute display metadata for a single tool_call event (streaming)."""
    is_tell = tool_call_name in _TELL_OWNER_TOOLS
    return {"showing": latent == "owner" or is_tell, "is_tell_owner": is_tell}


def project_thread_display(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """Annotate each message with display metadata for Thread owner view.

    Pure function: f(messages) → (annotated_messages, final_latent).
    """
    latent = "owner"

    for msg in messages:
        msg_type = msg.get("type", "")
        meta = msg.get("metadata") or {}

        if msg_type == "HumanMessage":
            source = meta.get("source", "owner")
            is_steer = bool(meta.get("is_steer"))
            showing, latent = compute_showing(source, is_steer, latent)
            msg["display"] = {"showing": showing}

        elif msg_type == "AIMessage":
            tc_names = [tc.get("name", "") for tc in msg.get("tool_calls", [])]
            msg["display"] = ai_display(latent, tc_names)

        elif msg_type == "ToolMessage":
            tool_name = meta.get("name") or msg.get("name") or ""
            msg["display"] = tool_display(latent, tool_name)

        else:
            msg["display"] = {"showing": latent == "owner"}

    return messages, latent
