"""Monitor trace read-source boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from backend.web.services.agent_pool import resolve_thread_sandbox
from backend.web.services.thread_history_service import build_thread_history_transport, get_thread_history_payload
from storage.runtime import build_storage_container


@dataclass(frozen=True)
class MonitorTraceReader:
    load_thread_history_payload: Callable[[str], Awaitable[dict[str, Any]]]
    load_latest_run_events: Callable[[str], tuple[str | None, list[dict[str, Any]]]]


def build_monitor_trace_reader(app: Any) -> MonitorTraceReader:
    history_transport = build_thread_history_transport(
        resolve_sandbox=lambda thread_id: resolve_thread_sandbox(app, thread_id),
        agent_pool=getattr(app.state, "agent_pool", None),
        checkpoint_store=getattr(app.state, "thread_checkpoint_store", None),
    )

    async def _load_thread_history_payload(thread_id: str) -> dict[str, Any]:
        return await load_thread_history_payload(thread_id, history_transport=history_transport)

    return MonitorTraceReader(
        load_thread_history_payload=_load_thread_history_payload,
        load_latest_run_events=load_latest_run_events,
    )


async def load_thread_history_payload(thread_id: str, *, history_transport) -> dict[str, Any]:
    return await get_thread_history_payload(
        thread_id=thread_id,
        history_transport=history_transport,
        limit=200,
        truncate=0,
    )


def load_latest_run_events(thread_id: str) -> tuple[str | None, list[dict[str, Any]]]:
    container = build_storage_container()
    repo = container.run_event_repo()
    try:
        run_id = repo.latest_run_id(thread_id)
        if run_id is None:
            return None, []
        return run_id, repo.list_events(thread_id, run_id, after=0, limit=1000)
    finally:
        repo.close()
