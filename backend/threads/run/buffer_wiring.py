"""Thread buffer lifecycle and runtime handler wiring helpers."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from backend.threads.events.buffer import ThreadEventBuffer
from core.runtime.middleware.monitor import AgentState

logger = logging.getLogger(__name__)

_start_agent_run: Callable[..., Any] | None = None
_append_event: Callable[[str, str, dict[str, Any]], Awaitable[int]] | None = None


def get_or_create_thread_buffer(app: Any, thread_id: str) -> ThreadEventBuffer:
    """Get existing or create new ThreadEventBuffer for a thread."""
    buf = app.state.thread_event_buffers.get(thread_id)
    if isinstance(buf, ThreadEventBuffer):
        return buf
    buf = ThreadEventBuffer()
    app.state.thread_event_buffers[thread_id] = buf
    return buf


def ensure_thread_handlers(agent: Any, thread_id: str, app: Any) -> None:
    """Bind per-thread handlers (activity_sink, wake_handler) if not already set."""
    runtime = getattr(agent, "runtime", None)
    if not runtime:
        return
    if getattr(runtime, "_bound_thread_id", None) == thread_id and getattr(runtime, "_bound_thread_app", None) is app:
        return
    if not hasattr(runtime, "bind_thread"):
        return

    thread_buf = get_or_create_thread_buffer(app, thread_id)

    runtime_state = getattr(app.state, "threads_runtime_state", None)
    display_builder_ref = getattr(runtime_state, "display_builder", None)
    if display_builder_ref is None:
        raise RuntimeError("display_builder is required for thread buffer wiring")

    async def activity_sink(event: dict) -> None:
        if _append_event is None:
            raise RuntimeError("thread_runtime.run.buffer_wiring requires _append_event binding")
        seq = await _append_event(thread_id, f"activity_{thread_id}", event)
        try:
            data = json.loads(event.get("data", "{}")) if isinstance(event.get("data"), str) else event.get("data", {})
        except (json.JSONDecodeError, TypeError):
            data = event.get("data", {})
        if isinstance(data, dict):
            data["_seq"] = seq
            event = {**event, "data": json.dumps(data, ensure_ascii=False)}
        _sse_fields = frozenset({"event", "data", "id", "retry", "comment"})
        sse_event = {k: v for k, v in event.items() if k in _sse_fields}
        await thread_buf.put(sse_event)

        event_type = sse_event.get("event", "")
        if event_type and isinstance(data, dict):
            delta = display_builder_ref.apply_event(thread_id, event_type, data)
            if delta:
                delta["_seq"] = seq
                await thread_buf.put(
                    {
                        "event": "display_delta",
                        "data": json.dumps(delta, ensure_ascii=False),
                    }
                )

    qm = app.state.queue_manager
    loop = getattr(runtime_state, "event_loop", None)

    def wake_handler(item: Any) -> None:
        """Called by enqueue() with the newly-enqueued QueueItem — may run in any thread."""
        if not (hasattr(agent, "runtime") and agent.runtime.transition(AgentState.ACTIVE)):
            source = getattr(item, "source", None)
            if loop and not loop.is_closed():

                async def _emit_active_event() -> None:
                    if source == "owner":
                        await activity_sink(
                            {
                                "event": "user_message",
                                "data": json.dumps(
                                    {
                                        "content": item.content,
                                        "showing": True,
                                    },
                                    ensure_ascii=False,
                                ),
                            }
                        )

                loop.call_soon_threadsafe(loop.create_task, _emit_active_event())
            return

        item = qm.dequeue(thread_id)
        if not item:
            logger.warning(
                "wake_handler: dequeue returned None for thread %s (race with drain_all), reverting to IDLE",
                thread_id,
            )
            if hasattr(agent, "runtime"):
                agent.runtime.transition(AgentState.IDLE)
            return

        async def _start_run():
            try:
                if _start_agent_run is None:
                    raise RuntimeError("thread_runtime.run.buffer_wiring requires _start_agent_run binding")
                _start_agent_run(
                    agent,
                    thread_id,
                    item.content,
                    app,
                    message_metadata={
                        "source": getattr(item, "source", None) or "system",
                        "notification_type": item.notification_type,
                        "sender_name": getattr(item, "sender_name", None),
                        "sender_avatar_url": getattr(item, "sender_avatar_url", None),
                        "is_steer": getattr(item, "is_steer", False),
                    },
                )
            except Exception:
                logger.error("wake_handler failed for thread %s", thread_id, exc_info=True)
                if hasattr(agent, "runtime"):
                    agent.runtime.transition(AgentState.IDLE)

        if loop and not loop.is_closed():
            loop.call_soon_threadsafe(loop.create_task, _start_run())
        else:
            logger.warning("wake_handler: no event loop for thread %s", thread_id)
            if hasattr(agent, "runtime"):
                agent.runtime.transition(AgentState.IDLE)

    runtime.bind_thread(activity_sink=activity_sink)
    runtime._bound_thread_id = thread_id
    runtime._bound_thread_app = app
    qm.register_wake(thread_id, wake_handler)

    try:
        from backend.threads.event_bus import get_event_bus

        unsubscribe = getattr(runtime, "_thread_event_unsubscribe", None)
        if callable(unsubscribe):
            unsubscribe()
        runtime._thread_event_unsubscribe = get_event_bus().subscribe(thread_id, activity_sink)
    except ImportError:
        pass
