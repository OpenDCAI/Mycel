"""Thread display projection — pure function from messages to annotated messages.

@@@display-projection — computes display_mode for each message based on
run source, tell_owner/ask_owner tool calls, and owner steer (waterline).

4 situations (Thread owner view):
1. Owner run → expanded
2. External run → collapsed
3. External run + tell_owner → collapsed, tell_owner punch_through
4. External run + owner steer → collapsed | waterline | expanded

NOTE: run_id is NOT reliably in message metadata (A6 patch disabled).
Instead, we infer "run segments" from HumanMessage boundaries.
Each HumanMessage starts a new segment. Its source determines display mode
for all following AI/Tool messages until the next HumanMessage.
"""

from __future__ import annotations

from typing import Any

_PUNCH_TOOLS = frozenset({"tell_owner", "ask_owner"})


def project_thread_display(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Annotate each message with display metadata for Thread owner view.

    Pure function: f(messages) → annotated_messages.
    Infers run segments from HumanMessage boundaries + source field.
    """
    # Current segment state
    segment_source: str | None = None  # "owner" | "external" | None
    segment_sender: str | None = None

    for msg in messages:
        msg_type = msg.get("type", "")
        meta = msg.get("metadata") or {}

        if msg_type == "HumanMessage":
            source = meta.get("source")
            sender_name = meta.get("sender_name")

            if source == "external":
                # New external segment
                segment_source = "external"
                segment_sender = sender_name
                msg["display"] = _display("collapsed", segment_source, segment_sender)

            elif source == "owner":
                if segment_source == "external":
                    # @@@waterline — owner steers into an external run
                    msg["display"] = _display("waterline", "owner", None)
                    segment_source = "owner"
                    segment_sender = None
                else:
                    # Normal owner message
                    segment_source = "owner"
                    segment_sender = None
                    msg["display"] = _display("expanded", "owner", None)

            else:
                # system or unknown — treat as owner
                segment_source = meta.get("source") or "owner"
                segment_sender = None
                msg["display"] = _display("expanded", segment_source, None)

        elif msg_type == "AIMessage":
            if segment_source == "external":
                # Check for tell_owner/ask_owner punch-through
                if _has_punch_tool(msg):
                    msg["display"] = _display("punch_through", segment_source, segment_sender)
                else:
                    msg["display"] = _display("collapsed", segment_source, segment_sender)
            else:
                msg["display"] = _display("expanded", segment_source, segment_sender)

        elif msg_type == "ToolMessage":
            if segment_source == "external":
                # Check if this is a tell_owner/ask_owner result
                tool_name = (meta.get("name") or msg.get("name") or "")
                if tool_name in _PUNCH_TOOLS:
                    msg["display"] = _display("punch_through", segment_source, segment_sender)
                else:
                    msg["display"] = _display("collapsed", segment_source, segment_sender)
            else:
                msg["display"] = _display("expanded", segment_source, segment_sender)

        else:
            # SystemMessage or other
            msg["display"] = _display("expanded", segment_source, segment_sender)

    return messages


def _display(mode: str, run_source: str | None, sender_name: str | None) -> dict[str, Any]:
    return {
        "mode": mode,
        "run_source": run_source,
        "sender_name": sender_name,
    }


def _has_punch_tool(msg: dict[str, Any]) -> bool:
    """Check if an AIMessage has tell_owner or ask_owner tool calls."""
    for tc in msg.get("tool_calls", []):
        if tc.get("name") in _PUNCH_TOOLS:
            return True
    return False
