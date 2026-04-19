"""Monitor trace read-source boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from backend.run_event_reads import build_run_event_read_transport
from backend.thread_history import build_thread_history_transport, get_thread_history_payload
from backend.thread_sandbox import resolve_thread_sandbox
from sandbox.thread_context import set_current_thread_id


@dataclass(frozen=True)
class MonitorTraceReader:
    load_thread_history_payload: Callable[[str], Awaitable[dict[str, Any]]]
    load_latest_run_events: Callable[[str], tuple[str | None, list[dict[str, Any]]]]


def build_monitor_trace_reader(app: Any) -> MonitorTraceReader:
    async def _load_live_messages(thread_id: str) -> list[Any] | None:
        agent_pool = getattr(app.state, "agent_pool", None)
        if not isinstance(agent_pool, dict):
            raise RuntimeError("agent_pool is required for thread history reads")

        sandbox_type = resolve_thread_sandbox(app, thread_id)
        agent = agent_pool.get(f"{thread_id}:{sandbox_type}")
        if agent is None:
            return None

        state = await agent.agent.aget_state({"configurable": {"thread_id": thread_id}})
        values = getattr(state, "values", {}) if state else {}
        messages = values.get("messages", []) if isinstance(values, dict) else []
        return list(messages)

    async def _load_checkpoint_messages(thread_id: str) -> list[Any]:
        checkpoint_store = getattr(app.state, "thread_checkpoint_store", None)
        if checkpoint_store is None:
            raise RuntimeError("thread_checkpoint_store is required for cold thread history reads")
        checkpoint_state = await checkpoint_store.load(thread_id)
        return list(checkpoint_state.messages) if checkpoint_state is not None else []

    history_transport = build_thread_history_transport(
        load_live_messages=_load_live_messages,
        load_checkpoint_messages=_load_checkpoint_messages,
    )

    async def _load_thread_history_payload(thread_id: str) -> dict[str, Any]:
        return await load_thread_history_payload(thread_id, history_transport=history_transport)

    return MonitorTraceReader(
        load_thread_history_payload=_load_thread_history_payload,
        load_latest_run_events=load_latest_run_events,
    )


async def load_thread_history_payload(thread_id: str, *, history_transport) -> dict[str, Any]:
    set_current_thread_id(thread_id)
    return await get_thread_history_payload(
        thread_id=thread_id,
        history_transport=history_transport,
        limit=200,
        truncate=0,
    )


def load_latest_run_events(thread_id: str) -> tuple[str | None, list[dict[str, Any]]]:
    transport = build_run_event_read_transport()
    run_id = transport.latest_run_id(thread_id)
    if run_id is None:
        return None, []
    return run_id, transport.list_events(thread_id, run_id, after=0, limit=1000)
