"""Run entrypoint helpers for thread runtime streaming."""

from __future__ import annotations

import asyncio
import json
import uuid as _uuid
from typing import Any

from backend.threads.message_content import extract_text_content
from backend.threads.run.buffer_wiring import ensure_thread_handlers, get_or_create_thread_buffer
from backend.threads.sandbox_resolution import resolve_thread_sandbox
from core.runtime.middleware.monitor import AgentState

_ensure_thread_handlers = ensure_thread_handlers
_get_or_create_thread_buffer = get_or_create_thread_buffer
_resolve_thread_sandbox = resolve_thread_sandbox
_extract_text_content = extract_text_content
_run_agent_to_buffer = None
_start_agent_run = None


def start_agent_run(
    agent: Any,
    thread_id: str,
    message: str,
    app: Any,
    enable_trajectory: bool = False,
    message_metadata: dict[str, Any] | None = None,
    input_messages: list[Any] | None = None,
) -> str:
    """Launch agent producer on the persistent ThreadEventBuffer. Returns run_id."""
    thread_buf = _get_or_create_thread_buffer(app, thread_id)
    run_id = str(_uuid.uuid4())
    if _run_agent_to_buffer is None:
        raise RuntimeError("thread_runtime.run.entrypoints requires _run_agent_to_buffer binding")
    bg_task = asyncio.create_task(
        _run_agent_to_buffer(
            agent,
            thread_id,
            message,
            app,
            enable_trajectory,
            thread_buf,
            run_id,
            message_metadata,
            input_messages,
        )
    )
    app.state.thread_tasks[thread_id] = bg_task
    return run_id


_start_agent_run = start_agent_run


async def run_child_thread_live(
    agent: Any,
    thread_id: str,
    message: str,
    app: Any,
    *,
    input_messages: list[Any],
) -> str:
    """Run a spawned child agent through the normal web thread path."""
    sandbox_type = _resolve_thread_sandbox(app, thread_id)
    pool_key = f"{thread_id}:{sandbox_type}"
    app.state.agent_pool[pool_key] = agent
    thread_buf = _get_or_create_thread_buffer(app, thread_id)
    error_cursor = thread_buf.total_count
    _ensure_thread_handlers(agent, thread_id, app)
    if not (hasattr(agent, "runtime") and agent.runtime.transition(AgentState.ACTIVE)):
        raise RuntimeError(f"Child thread {thread_id} could not transition to active")
    try:
        if _start_agent_run is None:
            raise RuntimeError("thread_runtime.run.entrypoints requires _start_agent_run binding")
        _start_agent_run(
            agent,
            thread_id,
            message,
            app,
            input_messages=input_messages,
        )
        task = app.state.thread_tasks[thread_id]
        result = await task
        recent_events, _ = await thread_buf.read_with_timeout(error_cursor, timeout=0.01)
        if recent_events:
            for event in recent_events:
                if event.get("event") != "error":
                    continue
                try:
                    payload = json.loads(event.get("data", "{}"))
                except (json.JSONDecodeError, TypeError):
                    payload = {}
                error_text = payload.get("error") if isinstance(payload, dict) else None
                raise RuntimeError(error_text or f"Child thread {thread_id} failed")
        if isinstance(result, str) and result.strip():
            return result.strip()

        state = await agent.agent.aget_state({"configurable": {"thread_id": thread_id}})
        values = getattr(state, "values", {}) if state else {}
        messages = values.get("messages", []) if isinstance(values, dict) else []
        visible_ai = [
            _extract_text_content(getattr(msg, "content", "")).strip()
            for msg in messages
            if msg.__class__.__name__ == "AIMessage" and _extract_text_content(getattr(msg, "content", "")).strip()
        ]
        runtime_status = agent.runtime.get_status_dict() if hasattr(agent, "runtime") and hasattr(agent.runtime, "get_status_dict") else {}
        runtime_tokens = runtime_status.get("tokens") if isinstance(runtime_status, dict) else None
        runtime_calls = runtime_tokens.get("call_count") if isinstance(runtime_tokens, dict) else None
        if not visible_ai and runtime_calls == 0:
            raise RuntimeError(f"Child thread {thread_id} failed before first model call")
        return "\n".join(visible_ai) if visible_ai else "(Agent completed with no text output)"
    finally:
        app.state.agent_pool.pop(pool_key, None)
        agent.close(cleanup_sandbox=False)
