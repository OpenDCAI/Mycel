"""Thread selection policy for chat delivery into runtime-backed agents."""

from __future__ import annotations

from typing import Any

from backend.protocols.runtime_read import RuntimeThreadActivityReader

_LIVE_CHILD_STATES = {"initializing", "ready", "active", "idle", "suspended"}


def select_runtime_thread_for_recipient(
    recipient_user_id: str,
    *,
    thread_repo: Any,
    activity_reader: RuntimeThreadActivityReader,
) -> str | None:
    thread = thread_repo.get_by_user_id(recipient_user_id)
    active_thread_id = _resolve_unique_active_thread_id(
        recipient_user_id,
        thread,
        thread_repo=thread_repo,
        activity_reader=activity_reader,
    )
    if active_thread_id is not None:
        return active_thread_id
    if thread is None:
        return None
    return str(thread["id"])


def _resolve_unique_active_thread_id(
    recipient_user_id: str,
    thread: dict[str, Any] | None,
    *,
    thread_repo: Any,
    activity_reader: RuntimeThreadActivityReader,
) -> str | None:
    agent_user_id = str((thread or {}).get("agent_user_id") or recipient_user_id).strip()
    if not agent_user_id:
        return None

    active_thread_ids: list[str] = []
    live_child_threads: list[tuple[int, str]] = []
    by_thread_id = {activity.thread_id: activity for activity in activity_reader.list_active_threads_for_agent(agent_user_id)}
    for candidate in thread_repo.list_by_agent_user(agent_user_id):
        thread_id = str(candidate.get("id") or "").strip()
        if not thread_id:
            continue
        activity = by_thread_id.get(thread_id)
        if activity is None:
            continue
        # @@@active-thread-delivery-precedence - fresh chat delivery should prefer a
        # recipient's latest live child thread over the default-main thread, even when the
        # main thread is still marked ACTIVE from stale work or older child threads still exist.
        if activity.state in _LIVE_CHILD_STATES and not activity.is_main:
            live_child_threads.append((activity.branch_index, thread_id))
        if activity.state == "active":
            active_thread_ids.append(thread_id)

    if live_child_threads:
        return max(live_child_threads)[1]
    unique_active_thread_ids = list(dict.fromkeys(active_thread_ids))
    if len(unique_active_thread_ids) == 1:
        return unique_active_thread_ids[0]
    return None
