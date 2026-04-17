"""Owner-visible thread runtime convergence.

This service keeps owner-facing thread surfaces aligned with the current
thread runtime contract instead of leaking incomplete thread rows.
"""

from __future__ import annotations

from typing import Any

from backend.web.services.thread_runtime_binding_service import ThreadRuntimeBindingError, resolve_thread_runtime_binding
from backend.web.utils.helpers import delete_thread_in_db


def purge_incomplete_owner_thread(app: Any, thread_id: str) -> None:
    # @@@incomplete-thread-purge - visible threads that cannot satisfy the
    # current thread->workspace->sandbox runtime binding should be removed once,
    # not kept alive behind endpoint-level repair guesses.
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
    """Check an owner-visible thread against the runtime contract without mutating thread rows."""

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
    """Converge an owner-visible thread to the current runtime contract.

    Returns one of:
    - ``missing``: no thread row exists
    - ``ready``: workspace/sandbox runtime binding is present
    - ``purged``: incomplete thread was deleted
    """

    runtime_state = inspect_owner_thread_runtime(app, thread_id)
    if runtime_state != "incomplete":
        return runtime_state

    purge_incomplete_owner_thread(app, thread_id)
    return "purged"


def summarize_owner_thread_runtime(app: Any, thread_ids: list[str]) -> dict[str, str]:
    """Batch-converge owner-visible threads against the workspace/sandbox runtime binding."""
    states: dict[str, str] = {}
    for thread_id in thread_ids:
        state = inspect_owner_thread_runtime(app, thread_id)
        if state == "incomplete":
            purge_incomplete_owner_thread(app, thread_id)
            state = "purged"
        states[thread_id] = state
    return states
