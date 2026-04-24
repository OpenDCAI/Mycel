from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from backend.identity.avatar.urls import avatar_url
from backend.threads.convergence import converge_owner_thread_runtime
from backend.threads.projection import canonical_owner_threads
from core.runtime.middleware.monitor import AgentState


@dataclass(frozen=True)
class OwnerThreadWorkbenchReader:
    list_owner_thread_rows: Callable[[str], list[dict[str, Any]]]
    converge_runtime_state: Callable[[str], str]
    is_runtime_active: Callable[[str, str], bool]
    last_active_at: Callable[[str], str | None]
    canonical_owner_threads: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
    avatar_url: Callable[[str | None, bool], str | None]


def build_owner_thread_workbench_reader(app: Any) -> OwnerThreadWorkbenchReader:
    return OwnerThreadWorkbenchReader(
        list_owner_thread_rows=lambda user_id: app.state.thread_repo.list_by_owner_user_id(user_id),
        converge_runtime_state=lambda thread_id: converge_owner_thread_runtime(app, thread_id),
        is_runtime_active=lambda thread_id, sandbox_type: bool(
            (agent := app.state.agent_pool.get(f"{thread_id}:{sandbox_type}"))
            and hasattr(agent, "runtime")
            and agent.runtime.current_state == AgentState.ACTIVE
        ),
        last_active_at=lambda thread_id: (
            datetime.fromtimestamp(last_active, tz=UTC).isoformat()
            if (last_active := app.state.thread_last_active.get(thread_id))
            else None
        ),
        canonical_owner_threads=canonical_owner_threads,
        avatar_url=avatar_url,
    )
