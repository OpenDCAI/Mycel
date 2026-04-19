"""Owner thread workbench app-state read boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.web.services.thread_runtime_convergence import converge_owner_thread_runtime, summarize_owner_thread_runtime
from core.runtime.middleware.monitor import AgentState


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
