"""App-backed runtime thread activity reader."""

from __future__ import annotations

from typing import Any, Literal

from core.runtime.middleware.monitor import AgentState
from protocols.runtime_read import AgentThreadActivity


def _normalize_state(state: AgentState) -> Literal["initializing", "ready", "active", "idle", "suspended", "stopped", "destroyed"]:
    if state == AgentState.INITIALIZING:
        return "initializing"
    if state == AgentState.READY:
        return "ready"
    if state == AgentState.ACTIVE:
        return "active"
    if state == AgentState.IDLE:
        return "idle"
    if state == AgentState.SUSPENDED:
        return "suspended"
    return "stopped"


class AppRuntimeThreadActivityReader:
    """Read live runtime thread activity from app-backed state."""

    def __init__(self, *, thread_repo: Any, agent_pool: dict[str, Any]) -> None:
        self._thread_repo = thread_repo
        self._agent_pool = agent_pool

    def list_active_threads_for_agent(self, agent_user_id: str) -> list[AgentThreadActivity]:
        rows = self._thread_repo.list_by_agent_user(agent_user_id)
        activities: list[AgentThreadActivity] = []
        for row in rows:
            thread_id = str(row.get("id") or "").strip()
            if not thread_id:
                continue
            for pool_key, agent in self._agent_pool.items():
                if not str(pool_key).startswith(f"{thread_id}:"):
                    continue
                activities.append(
                    AgentThreadActivity(
                        thread_id=thread_id,
                        is_main=bool(row.get("is_main")),
                        branch_index=int(row.get("branch_index") or 0),
                        state=_normalize_state(agent.runtime.current_state),
                    )
                )
                break
        return activities
