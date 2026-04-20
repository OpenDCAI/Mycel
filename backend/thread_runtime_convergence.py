"""Compatibility shell for thread runtime convergence helpers."""

from backend.thread_runtime import convergence as _owner


def _delete_thread_proxy(thread_id: str) -> None:
    from backend.web.services import thread_runtime_convergence as _shell

    _shell.delete_thread_in_db(thread_id)


_owner.delete_thread_in_db = _delete_thread_proxy

inspect_owner_thread_runtime = _owner.inspect_owner_thread_runtime
purge_incomplete_owner_thread = _owner.purge_incomplete_owner_thread
converge_owner_thread_runtime = _owner.converge_owner_thread_runtime
summarize_owner_thread_runtime = _owner.summarize_owner_thread_runtime

__all__ = [
    "inspect_owner_thread_runtime",
    "purge_incomplete_owner_thread",
    "converge_owner_thread_runtime",
    "summarize_owner_thread_runtime",
]
