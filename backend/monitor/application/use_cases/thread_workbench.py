"""Owner thread workbench projection."""

from __future__ import annotations

from backend.monitor.infrastructure.read_models.thread_workbench_read_service import OwnerThreadWorkbenchReader
from backend.web.services.thread_visibility import canonical_owner_threads
from backend.web.utils.serializers import avatar_url


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


def build_owner_thread_workbench(user_id: str, *, reader: OwnerThreadWorkbenchReader) -> dict[str, object]:
    raw = reader.list_owner_thread_rows(user_id)
    return build_owner_thread_workbench_from_rows(raw, reader=reader)


def build_owner_thread_workbench_from_rows(raw: list[dict[str, object]], *, reader: OwnerThreadWorkbenchReader) -> dict[str, object]:
    runtime_states = reader.summarize_runtime_states(raw)
    visible_threads = []
    for thread in raw:
        thread_id = thread["id"]
        runtime_state = runtime_states.get(thread_id) or reader.converge_runtime_state(thread_id)
        if runtime_state in {"missing", "purged"}:
            continue
        if is_internal_child_thread(thread_id):
            continue
        visible_threads.append(thread)

    threads = []
    for thread in canonical_owner_threads(visible_threads):
        thread_id = thread["id"]
        sandbox_type = thread.get("sandbox_type", "local")
        running = reader.is_runtime_active(thread_id, sandbox_type)
        updated_at = reader.last_active_at(thread_id)

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
