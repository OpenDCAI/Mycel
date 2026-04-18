"""Monitor trace read-source boundary."""

from __future__ import annotations

from typing import Any

from backend.web.services.thread_history_service import get_thread_history_payload
from storage.runtime import build_storage_container


async def load_thread_history_payload(app: Any, thread_id: str) -> dict[str, Any]:
    return await get_thread_history_payload(app=app, thread_id=thread_id, limit=200, truncate=0)


def load_latest_run_events(thread_id: str) -> tuple[str | None, list[dict[str, Any]]]:
    container = build_storage_container()
    repo = container.run_event_repo()
    try:
        run_id = repo.latest_run_id(thread_id)
        if run_id is None:
            return None, []
        return run_id, repo.list_events(thread_id, run_id, after=0, limit=1000)
    finally:
        repo.close()
