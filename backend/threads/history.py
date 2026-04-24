from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from backend.threads.interruption import repair_interrupted_tool_call_messages
from backend.threads.message_content import extract_text_content


def _trunc(text: str, truncate: int) -> str:
    if truncate > 0 and len(text) > truncate:
        return text[:truncate] + f"…[+{len(text) - truncate}]"
    return text


def _expand_history_message(msg: Any, truncate: int) -> list[dict[str, Any]]:
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


def build_thread_history_payload_from_display_entries(
    *,
    thread_id: str,
    entries: list[dict[str, Any]],
    limit: int = 20,
    truncate: int = 300,
) -> dict[str, Any]:
    visible_entries: list[dict[str, Any]] = []
    for entry in entries:
        role = entry.get("role")
        if role == "user":
            if entry.get("showing", True) is False:
                continue
            visible_entries.append(entry)
            continue
        if role in {"assistant", "notice"}:
            visible_entries.append(entry)

    selected_entries = visible_entries[-limit:] if limit > 0 else visible_entries
    flat: list[dict[str, Any]] = []

    for entry in selected_entries:
        role = entry.get("role")
        if role == "notice":
            text = entry.get("content")
            if isinstance(text, str) and text:
                flat.append({"role": "notification", "text": _trunc(text, truncate)})
            continue

        if role == "user":
            text = entry.get("content")
            if isinstance(text, str) and text:
                flat.append({"role": "human", "text": _trunc(text, truncate)})
            continue

        if role != "assistant":
            continue

        for segment in entry.get("segments", []):
            segment_type = segment.get("type")
            if segment_type == "notice":
                text = segment.get("content")
                if isinstance(text, str) and text:
                    flat.append({"role": "notification", "text": _trunc(text, truncate)})
                continue

            if segment_type == "text":
                text = segment.get("content")
                if isinstance(text, str) and text:
                    flat.append({"role": "assistant", "text": _trunc(text, truncate)})
                continue

            if segment_type != "tool":
                continue

            step = segment.get("step") or {}
            tool_name = str(step.get("name") or "?")
            flat.append(
                {
                    "role": "tool_call",
                    "tool": tool_name,
                    "args": _trunc(str(step.get("args", {})), truncate if truncate > 0 else 200),
                }
            )
            result = step.get("result")
            if isinstance(result, str) and result:
                flat.append(
                    {
                        "role": "tool_result",
                        "tool": tool_name,
                        "text": _trunc(result, truncate),
                    }
                )

    total = len(visible_entries)
    messages = flat
    return {
        "thread_id": thread_id,
        "total": total,
        "showing": len(selected_entries),
        "messages": messages,
    }


async def get_thread_history_payload(
    *,
    thread_id: str,
    load_live_messages: Callable[[str], Awaitable[list[Any] | None]],
    load_checkpoint_messages: Callable[[str], Awaitable[list[Any]]],
    limit: int = 20,
    truncate: int = 300,
) -> dict[str, Any]:
    live_messages = await load_live_messages(thread_id)
    if live_messages is None:
        all_messages = await load_checkpoint_messages(thread_id)
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
