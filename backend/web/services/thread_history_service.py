"""Shared thread history read surface."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from backend.web.services.thread_message_interruption_service import repair_interrupted_tool_call_messages
from backend.web.utils.serializers import extract_text_content


@dataclass(frozen=True)
class ThreadHistoryTransport:
    load_live_messages: Callable[[str], Awaitable[list[Any] | None]]
    load_checkpoint_messages: Callable[[str], Awaitable[list[Any]]]


def build_thread_history_transport(
    *,
    load_live_messages: Callable[[str], Awaitable[list[Any] | None]],
    load_checkpoint_messages: Callable[[str], Awaitable[list[Any]]],
) -> ThreadHistoryTransport:
    return ThreadHistoryTransport(
        load_live_messages=load_live_messages,
        load_checkpoint_messages=load_checkpoint_messages,
    )


def _trunc(text: str, truncate: int) -> str:
    if truncate > 0 and len(text) > truncate:
        return text[:truncate] + f"…[+{len(text) - truncate}]"
    return text


def _expand_history_message(msg: Any, truncate: int) -> list[dict[str, Any]]:
    """Flatten LangChain messages into the operator-facing history ledger."""
    cls = msg.__class__.__name__
    if cls == "HumanMessage":
        metadata = getattr(msg, "metadata", {}) or {}
        if metadata.get("source") == "internal":
            return []
        if metadata.get("source") == "system":
            return [{"role": "notification", "text": _trunc(extract_text_content(msg.content), truncate)}]
        return [{"role": "human", "text": _trunc(extract_text_content(msg.content), truncate)}]
    if cls == "AIMessage":
        entries: list[dict[str, Any]] = []
        for call in getattr(msg, "tool_calls", []):
            entries.append(
                {
                    "role": "tool_call",
                    "tool": call["name"],
                    "args": str(call.get("args", {}))[:200],
                }
            )
        text = extract_text_content(msg.content)
        if text:
            entries.append({"role": "assistant", "text": _trunc(text, truncate)})
        return entries
    if cls == "ToolMessage":
        return [
            {
                "role": "tool_result",
                "tool": getattr(msg, "name", "?"),
                "text": _trunc(extract_text_content(msg.content), truncate),
            }
        ]
    return [{"role": "system", "text": _trunc(extract_text_content(msg.content), truncate)}]


async def get_thread_history_payload(
    *,
    thread_id: str,
    history_transport: ThreadHistoryTransport,
    limit: int = 20,
    truncate: int = 300,
) -> dict[str, Any]:
    live_messages = await history_transport.load_live_messages(thread_id)
    if live_messages is None:
        all_messages = await history_transport.load_checkpoint_messages(thread_id)
    else:
        all_messages = live_messages
    all_messages = repair_interrupted_tool_call_messages(list(all_messages))
    total = len(all_messages)
    messages = all_messages[-limit:] if limit > 0 else all_messages

    flat: list[dict[str, Any]] = []
    for message in messages:
        flat.extend(_expand_history_message(message, truncate))

    return {
        "thread_id": thread_id,
        "total": total,
        "showing": len(messages),
        "messages": flat,
    }
