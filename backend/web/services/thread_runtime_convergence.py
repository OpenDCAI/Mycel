"""Owner-visible thread runtime convergence.

This service keeps owner-facing thread surfaces aligned with the current
thread runtime contract instead of leaking legacy half-bound thread rows.
"""

from __future__ import annotations

from typing import Any

from backend.web.utils.helpers import delete_thread_in_db


def purge_incomplete_owner_thread(app: Any, thread_id: str) -> None:
    # @@@legacy-thread-purge - legacy visible threads that cannot satisfy the
    # current thread->terminal->lease->volume contract should be removed once,
    # not kept alive behind endpoint-level fallbacks.
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


def converge_owner_thread_runtime(app: Any, thread_id: str) -> str:
    """Converge an owner-visible thread to the current runtime contract.

    Returns one of:
    - ``missing``: no thread row exists
    - ``ready``: active terminal already present
    - ``repaired_pointer``: terminal rows exist and active pointer was restored
    - ``purged``: legacy incomplete thread was deleted
    """

    thread = app.state.thread_repo.get_by_id(thread_id)
    if thread is None:
        return "missing"

    terminal_repo = getattr(app.state, "terminal_repo", None)
    if terminal_repo is None:
        raise RuntimeError("terminal_repo is required for thread runtime convergence")

    active_terminal = terminal_repo.get_active(thread_id)
    if active_terminal is not None:
        return "ready"

    terminals = terminal_repo.list_by_thread(thread_id)
    if terminals:
        terminal_repo.set_active(thread_id, str(terminals[0]["terminal_id"]))
        return "repaired_pointer"

    purge_incomplete_owner_thread(app, thread_id)
    return "purged"
