"""Compatibility shell for owner-thread runtime convergence."""

from __future__ import annotations

from backend.thread_runtime import convergence as _owner
from backend.web.utils.helpers import delete_thread_in_db


def _delete_thread_proxy(thread_id: str) -> None:
    delete_thread_in_db(thread_id)


_owner.delete_thread_in_db = _delete_thread_proxy

inspect_owner_thread_runtime = _owner.inspect_owner_thread_runtime
purge_incomplete_owner_thread = _owner.purge_incomplete_owner_thread
converge_owner_thread_runtime = _owner.converge_owner_thread_runtime
summarize_owner_thread_runtime = _owner.summarize_owner_thread_runtime

__all__ = [
    "converge_owner_thread_runtime",
    "inspect_owner_thread_runtime",
    "purge_incomplete_owner_thread",
    "summarize_owner_thread_runtime",
    "delete_thread_in_db",
]
