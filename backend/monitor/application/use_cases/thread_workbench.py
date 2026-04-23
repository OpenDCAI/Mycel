"""Owner thread workbench projection."""

from __future__ import annotations

from backend.monitor.infrastructure.read_models.thread_workbench_read_service import OwnerThreadWorkbenchReader


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


def _group_visible_threads_by_agent(raw: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    groups: dict[str, list[dict[str, object]]] = {}
    for thread in raw:
        thread_id = str(thread.get("id") or "")
        if is_internal_child_thread(thread_id):
            continue
        agent_user_id = str(thread.get("agent_user_id") or "").strip()
        if not agent_user_id:
            raise RuntimeError(f"Owner-visible thread {thread_id or '<missing>'} is missing agent_user_id")
        if agent_user_id not in groups:
            groups[agent_user_id] = []
        groups[agent_user_id].append(thread)
    return groups


def _select_visible_thread(group: list[dict[str, object]], *, reader: OwnerThreadWorkbenchReader) -> dict[str, object] | None:
    remaining = list(group)
    while remaining:
        # @@@owner-thread-candidate-selection - pick the current best candidate for one agent,
        # inspect just that candidate, and only fall through when it is purged/missing.
        # This keeps user-surface selection correct without paying a full binding scan
        # across every historical branch before we know which thread could even surface.
        candidate = reader.canonical_owner_threads(remaining)[0]
        thread_id = candidate["id"]
        runtime_state = reader.converge_runtime_state(thread_id)
        if runtime_state not in {"missing", "purged"}:
            return candidate
        remaining = [thread for thread in remaining if thread["id"] != thread_id]
    return None


def build_owner_thread_workbench_from_rows(raw: list[dict[str, object]], *, reader: OwnerThreadWorkbenchReader) -> dict[str, object]:
    raw_index = {str(thread.get("id") or ""): index for index, thread in enumerate(raw)}
    threads = []
    # @@@lazy-owner-thread-selection - monitor only needs one visible thread per agent.
    # Choosing the best candidate lazily avoids N full runtime-binding inspections
    # across every historical branch before we even know which thread would surface.
    selected_threads = []
    for group in _group_visible_threads_by_agent(raw).values():
        thread = _select_visible_thread(group, reader=reader)
        if thread is None:
            continue
        selected_threads.append(thread)

    selected_threads.sort(key=lambda thread: raw_index.get(str(thread.get("id") or ""), 0))

    for thread in selected_threads:
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
                "avatar_url": reader.avatar_url(thread.get("agent_user_id"), bool(thread.get("agent_avatar"))),
                "is_main": thread.get("is_main", False),
                "running": running,
                "updated_at": updated_at,
            }
        )
    return {"threads": threads}
