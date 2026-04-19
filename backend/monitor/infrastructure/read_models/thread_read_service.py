"""Thread read-source boundary for Monitor."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.web.services.resource_common import thread_owners
from backend.web.services.thread_visibility import canonical_owner_threads
from storage.runtime import build_thread_repo


def load_canonical_live_thread_refs(raw_thread_ids: list[str], live_thread_ids: set[str]) -> list[dict[str, Any]]:
    if not live_thread_ids:
        return []

    repo = build_thread_repo()
    try:
        rows = repo.list_by_ids([thread_id for thread_id in raw_thread_ids if thread_id in live_thread_ids])
    finally:
        repo.close()

    canonical = canonical_owner_threads(rows)
    return [{"thread_id": str(row.get("id") or "").strip()} for row in canonical if str(row.get("id") or "").strip()]


def load_live_thread_ids(raw_thread_ids: list[str]) -> set[str]:
    unique = sorted({str(thread_id or "").strip() for thread_id in raw_thread_ids if str(thread_id or "").strip()})
    if not unique:
        return set()
    owners = thread_owners(unique)
    return {thread_id for thread_id in unique if (owners.get(thread_id) or {}).get("agent_user_id")}


def load_monitor_thread_base(app: Any, thread_id: str) -> dict[str, Any]:
    thread_repo = getattr(app.state, "thread_repo", None)
    if thread_repo is None:
        raise RuntimeError("thread_repo is required for monitor thread detail")

    thread = thread_repo.get_by_id(thread_id)
    if thread is None:
        raise KeyError(f"Thread not found: {thread_id}")

    owners = thread_owners(
        [thread_id],
        user_repo=getattr(app.state, "user_repo", None),
        thread_repo=thread_repo,
    )
    return {
        "thread": thread,
        "owner": owners.get(thread_id),
    }


def build_monitor_thread_base_loader(app: Any) -> Callable[[str], dict[str, Any]]:
    return lambda thread_id: load_monitor_thread_base(app, thread_id)
