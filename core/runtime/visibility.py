"""Owner visibility — determines which messages are visible to the thread owner.

@@@owner-visibility — two-layer state: context (internal) + showing (metadata).

visibility_context ∈ {"owner", "external"} — tracks whose turn we're in. Never leaves backend.
showing: bool — render instruction for frontend.

Lives in core/runtime/ because the visibility_context is owned by AgentRuntime
and consumed by SteeringMiddleware + streaming_service.
"""

from __future__ import annotations

from typing import Any

_TELL_OWNER_TOOLS = frozenset({"tell_owner"})


def compute_visibility(source: str, is_steer: bool, context: str) -> tuple[bool, str]:
    """Compute visibility for a HumanMessage. Returns (showing, new_context)."""
    if source == "owner":
        return True, "owner"
    if source == "external":
        new_context = context if is_steer else "external"
        return False, new_context
    # system — follow current context
    return context == "owner", context


def message_visibility(context: str, tool_names: list[str] | None = None) -> dict[str, Any]:
    """Compute visibility for AI/Tool messages. showing follows context only;
    is_tell_owner is metadata for frontend extraction."""
    is_tell = any(n in _TELL_OWNER_TOOLS for n in (tool_names or []))
    return {"showing": context == "owner", "is_tell_owner": is_tell}


def tool_event_visibility(context: str, tool_name: str) -> dict[str, Any]:
    """Compute visibility for a streaming tool_call event.
    Unlike message_visibility, tell_owner overrides showing to true."""
    is_tell = tool_name in _TELL_OWNER_TOOLS
    return {"showing": context == "owner" or is_tell, "is_tell_owner": is_tell}


def annotate_owner_visibility(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """Annotate each message with visibility metadata for the thread owner.

    NOTE: mutates the input list (adds msg["display"] in-place). Returns
    (same_list, final_context) for convenience.
    """
    context = "owner"

    for msg in messages:
        msg_type = msg.get("type", "")
        meta = msg.get("metadata") or {}

        if msg_type == "HumanMessage":
            source = meta.get("source", "owner")
            is_steer = bool(meta.get("is_steer"))
            showing, context = compute_visibility(source, is_steer, context)
            msg["display"] = {"showing": showing}

        elif msg_type == "AIMessage":
            tc_names = [tc.get("name", "") for tc in msg.get("tool_calls", [])]
            msg["display"] = message_visibility(context, tc_names)

        elif msg_type == "ToolMessage":
            tool_name = meta.get("name") or msg.get("name") or ""
            msg["display"] = message_visibility(context, [tool_name])

        else:
            msg["display"] = {"showing": context == "owner"}

    return messages, context
