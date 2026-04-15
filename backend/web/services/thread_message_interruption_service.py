"""Shared message-level interruption repair for cold thread reads."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import ToolMessage

_INTERRUPTED_RESULT = "Error: task was interrupted (server restart or timeout). Results unavailable."


def repair_interrupted_tool_call_messages(messages: list[Any]) -> list[Any]:
    matched_tool_call_ids = {
        str(getattr(msg, "tool_call_id"))
        for msg in messages
        if getattr(msg, "__class__", None).__name__ == "ToolMessage" and getattr(msg, "tool_call_id", None)
    }
    repaired: list[Any] = []

    for msg in messages:
        repaired.append(msg)
        if getattr(msg, "__class__", None).__name__ != "AIMessage":
            continue
        tool_calls = getattr(msg, "tool_calls", []) or []
        # @@@interrupted-tool-repair-order - insert synthetic interrupted ToolMessages
        # immediately after the owning AIMessage so cold detail/history rebuilds see
        # the same caller-visible sequence as live repair.
        for tc in tool_calls:
            tc_id = str(tc.get("id") or "").strip()
            if not tc_id or tc_id in matched_tool_call_ids:
                continue
            repaired.append(
                ToolMessage(
                    content=_INTERRUPTED_RESULT,
                    name=str(tc.get("name") or "tool"),
                    tool_call_id=tc_id,
                )
            )
            matched_tool_call_ids.add(tc_id)

    return repaired
