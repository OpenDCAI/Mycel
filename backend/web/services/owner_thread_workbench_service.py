"""Owner thread workbench projection."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.web.services.thread_runtime_convergence import converge_owner_thread_runtime, summarize_owner_thread_runtime
from backend.web.services.thread_visibility import canonical_owner_threads
from backend.web.utils.serializers import avatar_url
from core.runtime.middleware.monitor import AgentState


def is_internal_child_thread(thread_id: str) -> bool:
    return thread_id.startswith("subagent-")


def sidebar_label(*, is_main: bool, branch_index: int) -> str | None:
    if branch_index < 0:
        raise ValueError(f"branch_index must be >= 0, got {branch_index}")
    if is_main and branch_index != 0:
        raise ValueError(f"Default thread must have branch_index=0, got {branch_index}")
    if not is_main and branch_index == 0:
        raise ValueError("Child thread must have branch_index>0")
    return None


def build_owner_thread_workbench(app: Any, user_id: str) -> dict[str, Any]:
    raw = app.state.thread_repo.list_by_owner_user_id(user_id)
    return build_owner_thread_workbench_from_rows(app, raw)


def build_owner_thread_workbench_from_rows(app: Any, raw: list[dict[str, Any]]) -> dict[str, Any]:
    pool = app.state.agent_pool
    runtime_states = summarize_owner_thread_runtime(app, [str(thread.get("id") or "") for thread in raw if thread.get("id")])
    visible_threads = []
    for thread in raw:
        thread_id = thread["id"]
        runtime_state = runtime_states.get(thread_id) or converge_owner_thread_runtime(app, thread_id)
        if runtime_state in {"missing", "purged"}:
            continue
        if is_internal_child_thread(thread_id):
            continue
        visible_threads.append(thread)

    threads = []
    for thread in canonical_owner_threads(visible_threads):
        thread_id = thread["id"]
        sandbox_type = thread.get("sandbox_type", "local")
        running = False
        agent = pool.get(f"{thread_id}:{sandbox_type}")
        if agent and hasattr(agent, "runtime"):
            running = agent.runtime.current_state == AgentState.ACTIVE
        last_active = app.state.thread_last_active.get(thread_id)
        updated_at = datetime.fromtimestamp(last_active, tz=UTC).isoformat() if last_active else None

        threads.append(
            {
                "thread_id": thread_id,
                "sandbox": thread.get("sandbox_type", "local"),
                "agent_name": thread.get("agent_name"),
                "agent_user_id": thread.get("agent_user_id"),
                "branch_index": thread.get("branch_index"),
                "sidebar_label": sidebar_label(
                    is_main=bool(thread.get("is_main", False)),
                    branch_index=int(thread.get("branch_index", 0)),
                ),
                "avatar_url": avatar_url(thread.get("agent_user_id"), bool(thread.get("agent_avatar"))),
                "is_main": thread.get("is_main", False),
                "running": running,
                "updated_at": updated_at,
            }
        )
    return {"threads": threads}
