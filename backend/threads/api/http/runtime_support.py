"""Shared runtime/task helper functions for threads HTTP surfaces."""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.threads.activity_pool_service import get_or_create_agent
from backend.threads.events.store import get_latest_run_id, read_events_after
from backend.threads.interruption import repair_interrupted_tool_call_messages
from backend.threads.runtime_access import get_optional_messaging_service
from backend.threads.sandbox_resolution import resolve_thread_sandbox
from backend.web.utils.serializers import serialize_message
from core.runtime.middleware.monitor import AgentState
from sandbox.thread_context import set_current_thread_id

_IDLE_REPLAYABLE_RUN_EVENTS = frozenset({"error", "cancelled", "retry"})
logger = logging.getLogger(__name__)


def get_agent_for_thread(app: Any, thread_id: str) -> Any | None:
    pool = getattr(app.state, "agent_pool", None)
    if not isinstance(pool, dict):
        return None
    sandbox_type = None
    thread_sandbox = getattr(app.state, "thread_sandbox", None)
    if isinstance(thread_sandbox, dict):
        sandbox_type = thread_sandbox.get(thread_id)
    if sandbox_type:
        pool_key = f"{thread_id}:{sandbox_type}"
        agent = pool.get(pool_key)
        if agent is not None:
            return agent

    matches = [agent for pool_key, agent in pool.items() if str(pool_key).startswith(f"{thread_id}:")]
    if len(matches) == 1:
        return matches[0]
    if matches:
        return matches[0]
    return None


def checkpoint_tail_is_pending_owner_turn(messages: list[dict[str, Any]]) -> bool:
    if not messages:
        return False
    tail = messages[-1]
    if tail.get("type") != "HumanMessage":
        return False
    meta = tail.get("metadata") or {}
    return meta.get("source") not in {"system", "external"}


def display_entries_need_idle_rebuild(entries: list[dict[str, Any]], messages: list[dict[str, Any]]) -> bool:
    if not messages:
        return bool(entries)
    if not entries:
        return True
    return any(entry.get("role") == "assistant" and not entry.get("segments") for entry in entries)


def normalize_blocking_subagent_terminal_status(entries: list[dict[str, Any]]) -> None:
    for entry in entries:
        if entry.get("role") != "assistant":
            continue
        for seg in entry.get("segments", []):
            if seg.get("type") != "tool":
                continue
            step = seg.get("step") or {}
            if step.get("name") != "Agent" or step.get("status") != "done":
                continue
            stream = step.get("subagent_stream")
            if not isinstance(stream, dict):
                continue
            result_text = step.get("result")
            existing_status = str(stream.get("status") or "").lower()
            terminal_status = (
                existing_status
                if existing_status in {"completed", "error", "cancelled"}
                else ("error" if isinstance(result_text, str) and result_text.startswith("<tool_use_error>") else "completed")
            )
            if stream.get("status") != terminal_status:
                stream["status"] = terminal_status
            if terminal_status == "error" and not stream.get("error") and isinstance(result_text, str):
                stream["error"] = result_text


def collect_display_subagent_tasks(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if entry.get("role") != "assistant":
            continue
        for seg in entry.get("segments", []):
            if seg.get("type") != "tool":
                continue
            step = seg.get("step") or {}
            if step.get("name") != "Agent":
                continue
            stream = step.get("subagent_stream")
            if not isinstance(stream, dict) or not stream.get("task_id"):
                continue
            task_id = str(stream["task_id"])
            raw_args = step.get("args")
            args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
            description = stream.get("description") or args.get("description") or args.get("prompt")
            status = str(stream.get("status") or ("completed" if step.get("status") == "done" else "running"))
            result_text = step.get("result") or stream.get("text")
            tasks[task_id] = {
                "task_id": task_id,
                "task_type": "agent",
                "status": status,
                "command_line": None,
                "description": description,
                "exit_code": None,
                "error": stream.get("error"),
                "result": result_text,
                "text": result_text,
                "thread_id": stream.get("thread_id"),
            }
    return tasks


async def replay_latest_run_failure_events(
    *,
    thread_id: str,
    display_builder: Any,
) -> None:
    run_id = await get_latest_run_id(thread_id)
    if not run_id or run_id.startswith("activity_"):
        return

    events = await read_events_after(thread_id, run_id, 0)
    if not any(event.get("event") in _IDLE_REPLAYABLE_RUN_EVENTS for event in events):
        return

    for event in events:
        event_type = event.get("event", "")
        if event_type not in {"run_start", "run_done", *_IDLE_REPLAYABLE_RUN_EVENTS}:
            continue
        raw_data = event.get("data", "{}")
        try:
            payload = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        display_builder.apply_event(thread_id, event_type, payload)


async def _load_checkpoint_messages_for_detail(app: Any, thread_id: str) -> list[Any] | None:
    runtime_state = getattr(app.state, "threads_runtime_state", None)
    checkpoint_store = getattr(runtime_state, "checkpoint_store", None)
    if checkpoint_store is None:
        return None
    try:
        checkpoint_state = await checkpoint_store.load(thread_id)
    except Exception:
        logger.warning("Checkpoint detail fast-path failed for thread %s", thread_id, exc_info=True)
        return None
    if checkpoint_state is None:
        return []
    return list(checkpoint_state.messages)


async def _build_display_entries_from_messages(
    *,
    thread_id: str,
    messages: list[Any],
    display_builder: Any,
    existing_entries: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    messages = repair_interrupted_tool_call_messages(list(messages))
    serialized = [serialize_message(msg) for msg in messages]

    from core.runtime.visibility import annotate_owner_visibility

    annotated, _ = annotate_owner_visibility(serialized)
    if existing_entries is not None and not display_entries_need_idle_rebuild(existing_entries, annotated):
        return existing_entries
    entries = display_builder.build_from_checkpoint(thread_id, annotated)
    if checkpoint_tail_is_pending_owner_turn(annotated):
        await replay_latest_run_failure_events(
            thread_id=thread_id,
            display_builder=display_builder,
        )
        entries = display_builder.get_entries(thread_id) or entries
    normalize_blocking_subagent_terminal_status(entries)
    return entries


async def get_thread_display_entries(app: Any, thread_id: str) -> list[dict[str, Any]]:
    runtime_state = getattr(app.state, "threads_runtime_state", None)
    display_builder = getattr(runtime_state, "display_builder", None)
    if display_builder is None:
        raise RuntimeError("display_builder is required for thread display entries")
    entries = display_builder.get_entries(thread_id)
    if entries is not None:
        normalize_blocking_subagent_terminal_status(entries)
    agent = get_agent_for_thread(app, thread_id)
    if agent is not None and entries is not None and getattr(getattr(agent, "runtime", None), "current_state", None) != AgentState.IDLE:
        return entries
    if agent is None:
        checkpoint_messages = await _load_checkpoint_messages_for_detail(app, thread_id)
        if checkpoint_messages is not None:
            return await _build_display_entries_from_messages(
                thread_id=thread_id,
                messages=checkpoint_messages,
                display_builder=display_builder,
                existing_entries=entries,
            )
        sandbox_type = resolve_thread_sandbox(app, thread_id)
        agent = await get_or_create_agent(
            app,
            sandbox_type,
            thread_id=thread_id,
            messaging_service=get_optional_messaging_service(app),
        )

    set_current_thread_id(thread_id)
    config = {"configurable": {"thread_id": thread_id}}
    state = await agent.agent.aget_state(config)
    values = getattr(state, "values", {}) if state else {}
    messages = values.get("messages", []) if isinstance(values, dict) else []
    return await _build_display_entries_from_messages(
        thread_id=thread_id,
        messages=list(messages),
        display_builder=display_builder,
        existing_entries=entries,
    )
