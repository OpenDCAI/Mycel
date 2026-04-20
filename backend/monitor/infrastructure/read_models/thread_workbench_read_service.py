"""Owner thread workbench app-state read boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from backend.avatar_urls import avatar_url
from backend.thread_runtime.convergence import converge_owner_thread_runtime, summarize_owner_thread_runtime
from backend.thread_runtime.projection import canonical_owner_threads
from core.runtime.middleware.monitor import AgentState


@dataclass(frozen=True)
class OwnerThreadWorkbenchReader:
    list_owner_thread_rows: Callable[[str], list[dict[str, Any]]]
    summarize_runtime_states: Callable[[list[dict[str, Any]]], dict[str, str]]
    converge_runtime_state: Callable[[str], str]
    is_runtime_active: Callable[[str, str], bool]
    last_active_at: Callable[[str], str | None]
    canonical_owner_threads: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
    avatar_url: Callable[[str | None, bool], str | None]


def build_owner_thread_workbench_reader(app: Any) -> OwnerThreadWorkbenchReader:
    return OwnerThreadWorkbenchReader(
        list_owner_thread_rows=lambda user_id: list_owner_thread_rows(app, user_id),
        summarize_runtime_states=lambda raw: summarize_runtime_states(app, raw),
        converge_runtime_state=lambda thread_id: converge_runtime_state(app, thread_id),
        is_runtime_active=lambda thread_id, sandbox_type: is_runtime_active(app, thread_id, sandbox_type),
        last_active_at=lambda thread_id: last_active_at(app, thread_id),
        canonical_owner_threads=canonical_owner_threads,
        avatar_url=avatar_url,
    )


def list_owner_thread_rows(app: Any, user_id: str) -> list[dict[str, Any]]:
    return app.state.thread_repo.list_by_owner_user_id(user_id)


def summarize_runtime_states(app: Any, raw: list[dict[str, Any]]) -> dict[str, str]:
    return summarize_owner_thread_runtime(app, [str(thread.get("id") or "") for thread in raw if thread.get("id")])


def converge_runtime_state(app: Any, thread_id: str) -> str:
    return converge_owner_thread_runtime(app, thread_id)


def is_runtime_active(app: Any, thread_id: str, sandbox_type: str) -> bool:
    agent = app.state.agent_pool.get(f"{thread_id}:{sandbox_type}")
    return bool(agent and hasattr(agent, "runtime") and agent.runtime.current_state == AgentState.ACTIVE)


def last_active_at(app: Any, thread_id: str) -> str | None:
    last_active = app.state.thread_last_active.get(thread_id)
    return datetime.fromtimestamp(last_active, tz=UTC).isoformat() if last_active else None
