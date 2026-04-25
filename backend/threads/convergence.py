from __future__ import annotations

from typing import Any

from backend.threads.binding import ThreadRuntimeBindingError, resolve_thread_runtime_binding
from sandbox.control_plane_repos import make_chat_session_repo, make_terminal_repo, resolve_sandbox_db_path
from sandbox.sync.state import InMemorySyncFileBacking, SyncState
from storage.container_cache import get_storage_container as _get_container
from storage.runtime import uses_supabase_runtime_defaults


def delete_thread_in_db(thread_id: str) -> None:
    _get_container().purge_thread(thread_id)

    if not uses_supabase_runtime_defaults():
        sandbox_db = resolve_sandbox_db_path()
        if not sandbox_db.exists():
            return

    session_repo = make_chat_session_repo()
    terminal_repo = make_terminal_repo()
    sync_state = SyncState(repo=InMemorySyncFileBacking())
    try:
        session_repo.delete_by_thread(thread_id)
        terminal_repo.delete_by_thread(thread_id)
        sync_state.clear_thread(thread_id)
    finally:
        sync_state.close()
        session_repo.close()
        terminal_repo.close()


def purge_incomplete_owner_thread(app: Any, thread_id: str) -> None:
    # @@@incomplete-thread-purge - visible threads that cannot satisfy the
    # current thread->workspace->sandbox runtime binding are purged at the source.
    delete_thread_in_db(thread_id)
    app.state.thread_repo.delete(thread_id)

    for attr in ("thread_sandbox", "thread_cwd", "thread_event_buffers", "thread_tasks", "thread_last_active"):
        mapping = getattr(app.state, attr, None)
        if isinstance(mapping, dict):
            mapping.pop(thread_id, None)

    agent_pool = getattr(app.state, "agent_pool", None)
    if isinstance(agent_pool, dict):
        for pool_key in [key for key in agent_pool if key.startswith(f"{thread_id}:")]:
            agent_pool.pop(pool_key, None)

    queue_manager = getattr(app.state, "queue_manager", None)
    if queue_manager is not None and hasattr(queue_manager, "clear_all"):
        queue_manager.clear_all(thread_id)


def inspect_owner_thread_runtime(app: Any, thread_id: str) -> str:
    thread = app.state.thread_repo.get_by_id(thread_id)
    if thread is None:
        return "missing"

    try:
        resolve_thread_runtime_binding(
            thread_repo=app.state.thread_repo,
            workspace_repo=app.state.workspace_repo,
            sandbox_repo=app.state.sandbox_repo,
            thread_id=thread_id,
        )
        return "ready"
    except (AttributeError, ThreadRuntimeBindingError):
        return "incomplete"


def converge_owner_thread_runtime(app: Any, thread_id: str) -> str:
    runtime_state = inspect_owner_thread_runtime(app, thread_id)
    if runtime_state != "incomplete":
        return runtime_state

    purge_incomplete_owner_thread(app, thread_id)
    return "purged"


def summarize_owner_thread_runtime(app: Any, thread_ids: list[str]) -> dict[str, str]:
    states: dict[str, str] = {}
    for thread_id in thread_ids:
        state = inspect_owner_thread_runtime(app, thread_id)
        if state == "incomplete":
            purge_incomplete_owner_thread(app, thread_id)
            state = "purged"
        states[thread_id] = state
    return states
