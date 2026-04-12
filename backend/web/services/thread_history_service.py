"""Shared thread history read surface."""

from __future__ import annotations

from typing import Any

from backend.web.utils.serializers import extract_text_content


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
    app: Any,
    thread_id: str,
    limit: int = 20,
    truncate: int = 300,
) -> dict[str, Any]:
    from backend.web.routers.threads import resolve_thread_sandbox
    from sandbox.thread_context import set_current_thread_id

    sandbox_type = resolve_thread_sandbox(app, thread_id)
    set_current_thread_id(thread_id)
    pool = getattr(app.state, "agent_pool", None)
    if not isinstance(pool, dict):
        raise RuntimeError("agent_pool is required for thread history reads")

    agent = pool.get(f"{thread_id}:{sandbox_type}")
    if agent is not None:
        state = await agent.agent.aget_state({"configurable": {"thread_id": thread_id}})
        values = getattr(state, "values", {}) if state else {}
    else:
        checkpoint_store = getattr(app.state, "thread_checkpoint_store", None)
        if checkpoint_store is None:
            raise RuntimeError("thread_checkpoint_store is required for cold thread history reads")
        checkpoint_state = await checkpoint_store.load(thread_id)
        values = {"messages": list(checkpoint_state.messages) if checkpoint_state is not None else []}
    all_messages = values.get("messages", []) if isinstance(values, dict) else []
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
