"""Persistent run-event service via storage repository boundary."""

import asyncio
import json
from typing import Any

from storage.contracts import RunEventRepo
from storage.runtime import build_storage_container

_default_run_event_repo: RunEventRepo | None = None


def _resolve_run_event_repo(run_event_repo: RunEventRepo | None) -> RunEventRepo:
    if run_event_repo is not None:
        return run_event_repo

    global _default_run_event_repo
    if _default_run_event_repo is not None:
        return _default_run_event_repo

    # @@@event-store-single-path - keep one persistence boundary; when caller omits repo, resolve default repo from storage container.
    container = build_storage_container()
    _default_run_event_repo = container.run_event_repo()
    return _default_run_event_repo


async def append_event(
    thread_id: str,
    run_id: str,
    event: dict[str, Any],
    message_id: str | None = None,
    run_event_repo: RunEventRepo | None = None,
) -> int:
    """Persist one SSE event and return its sequence number."""
    repo = _resolve_run_event_repo(run_event_repo)
    payload = _event_payload_to_dict(event)
    return int(
        await asyncio.to_thread(
            repo.append_event,
            thread_id,
            run_id,
            event.get("event", ""),
            payload,
            message_id,
        )
    )


async def read_events_after(
    thread_id: str,
    run_id: str,
    after_seq: int = 0,
    run_event_repo: RunEventRepo | None = None,
) -> list[dict[str, Any]]:
    """Return events with seq > after_seq for the given run."""
    repo = _resolve_run_event_repo(run_event_repo)
    rows = await asyncio.to_thread(
        repo.list_events,
        thread_id,
        run_id,
        after=after_seq,
        limit=10000,
    )
    return [
        {
            "seq": row.get("seq"),
            "event": row.get("event_type", ""),
            "data": json.dumps(row.get("data", {}), ensure_ascii=False),
            "message_id": row.get("message_id"),
        }
        for row in rows
    ]


async def get_last_seq(thread_id: str, run_event_repo: RunEventRepo | None = None) -> int:
    """Return the highest seq for a thread, or 0."""
    repo = _resolve_run_event_repo(run_event_repo)
    return int(await asyncio.to_thread(repo.latest_seq, thread_id))


async def get_run_start_seq(thread_id: str, run_id: str, run_event_repo: RunEventRepo | None = None) -> int:
    """Return the first seq for a specific run, or 0."""
    repo = _resolve_run_event_repo(run_event_repo)
    return int(await asyncio.to_thread(repo.run_start_seq, thread_id, run_id))


async def get_latest_run_id(thread_id: str, run_event_repo: RunEventRepo | None = None) -> str | None:
    """Return the run_id of the most recent run for a thread, or None."""
    repo = _resolve_run_event_repo(run_event_repo)
    return await asyncio.to_thread(repo.latest_run_id, thread_id)


async def cleanup_old_runs(
    thread_id: str,
    keep_latest: int = 1,
    run_event_repo: RunEventRepo | None = None,
) -> int:
    """Delete all but the N most recent runs for a thread. Returns deleted count."""
    repo = _resolve_run_event_repo(run_event_repo)
    run_ids = await asyncio.to_thread(repo.list_run_ids, thread_id)
    if len(run_ids) <= keep_latest:
        return 0
    old_ids = run_ids[keep_latest:]
    # Preserve activity run_ids — they have per-thread lifetime, not per-run.
    old_ids = [rid for rid in old_ids if not rid.startswith("activity_")]
    if not old_ids:
        return 0
    return int(await asyncio.to_thread(repo.delete_runs, thread_id, old_ids))


def _event_payload_to_dict(event: dict[str, Any]) -> dict[str, Any]:
    raw_data = event.get("data", {})
    if isinstance(raw_data, dict):
        return raw_data
    if raw_data in (None, ""):
        return {}
    if not isinstance(raw_data, str):
        raise RuntimeError("Run event data must be a dict or JSON string when using storage_container run_event_repo.")
    try:
        payload = json.loads(raw_data)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Run event data must be valid JSON when using storage_container run_event_repo.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Run event data JSON must decode to an object when using storage_container run_event_repo.")
    return payload
