"""Monitor thread trajectory surface."""

from __future__ import annotations

from typing import Any

from backend.web.services.thread_history_service import get_thread_history_payload
from storage.runtime import build_storage_container


def _summarize_trace_event(event_type: str, payload: dict[str, Any]) -> str:
    if event_type == "tool_call":
        return str(payload.get("name") or "tool")
    if event_type == "tool_result":
        return str(payload.get("content") or "(no output)")
    if event_type == "text":
        return str(payload.get("content") or "")
    if event_type == "status":
        state = payload.get("state")
        state_text = state if isinstance(state, str) else str(state or "-")
        return f"state={state_text} calls={payload.get('call_count', '-')}"
    if event_type == "error":
        return str(payload.get("error") or "error")
    if event_type == "cancelled":
        return "cancelled"
    if event_type == "done":
        return "done"
    return str(payload)[:160]


def _normalize_trace_event(row: dict[str, Any], run_id: str) -> dict[str, Any] | None:
    event_type = str(row.get("event_type") or "")
    payload = row.get("data") or {}
    if not isinstance(payload, dict):
        payload = {}

    actor_map = {
        "text": "assistant",
        "tool_call": "tool",
        "tool_result": "tool",
        "status": "runtime",
        "error": "runtime",
        "cancelled": "runtime",
        "done": "runtime",
    }
    actor = actor_map.get(event_type)
    if actor is None:
        return None

    summary = _summarize_trace_event(event_type, payload)
    if not summary:
        return None

    normalized_type = "assistant_text" if event_type == "text" else event_type
    return {
        "seq": row.get("seq"),
        "run_id": run_id,
        "event_type": normalized_type,
        "actor": actor,
        "summary": summary,
        "payload": payload,
    }


def _merge_trace_events(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for item in items:
        last = merged[-1] if merged else None
        # @@@trajectory-text-fold - keep one assistant text block per contiguous stream so thread detail stays readable.
        if (
            last is not None
            and item["event_type"] == "assistant_text"
            and last["event_type"] == "assistant_text"
            and last["run_id"] == item["run_id"]
        ):
            last["seq"] = item["seq"]
            last["summary"] = f"{last['summary']}{item['summary']}"
            last["payload"] = item["payload"]
            continue
        if (
            last is not None
            and item["event_type"] == "status"
            and last["event_type"] == "status"
            and last["run_id"] == item["run_id"]
        ):
            merged[-1] = item
            continue
        merged.append(item)
    return merged


async def build_monitor_thread_trajectory(app: Any, thread_id: str) -> dict[str, Any]:
    history = await get_thread_history_payload(app=app, thread_id=thread_id, limit=200, truncate=0)

    container = build_storage_container()
    repo = container.run_event_repo()
    try:
        run_id = repo.latest_run_id(thread_id)
        if run_id is None:
            return {
                "run_id": None,
                "conversation": history["messages"],
                "events": [],
            }

        rows = repo.list_events(thread_id, run_id, after=0, limit=1000)
    finally:
        repo.close()

    normalized = [_normalize_trace_event(row, run_id) for row in rows]
    events = _merge_trace_events([item for item in normalized if item is not None])

    return {
        "run_id": run_id,
        "conversation": history["messages"],
        "events": events,
    }
