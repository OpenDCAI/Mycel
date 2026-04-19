"""Compatibility shell for thread runtime event store helpers."""

from typing import Any

from backend.thread_runtime.events import reads as _reads
from backend.thread_runtime.events import store as _store
from storage.contracts import RunEventRepo
from storage.runtime import build_storage_container

_default_run_event_repo: RunEventRepo | None = None
RunEventReadTransport = _reads.RunEventReadTransport


def _sync_owner_modules() -> None:
    _reads._default_run_event_repo = _default_run_event_repo
    _reads.build_storage_container = build_storage_container
    _store._default_run_event_repo = _default_run_event_repo
    _store.build_storage_container = build_storage_container


def build_run_event_read_transport(run_event_repo: RunEventRepo | None = None) -> RunEventReadTransport:
    _sync_owner_modules()
    return _reads.build_run_event_read_transport(run_event_repo)


async def append_event(*args: Any, **kwargs: Any) -> int:
    _sync_owner_modules()
    return await _store.append_event(*args, **kwargs)


async def read_events_after(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    _sync_owner_modules()
    return await _store.read_events_after(*args, **kwargs)


async def get_last_seq(*args: Any, **kwargs: Any) -> int:
    _sync_owner_modules()
    return await _store.get_last_seq(*args, **kwargs)


async def get_run_start_seq(*args: Any, **kwargs: Any) -> int:
    _sync_owner_modules()
    return await _store.get_run_start_seq(*args, **kwargs)


async def get_latest_run_id(*args: Any, **kwargs: Any) -> str | None:
    _sync_owner_modules()
    return await _store.get_latest_run_id(*args, **kwargs)


async def cleanup_old_runs(*args: Any, **kwargs: Any) -> int:
    _sync_owner_modules()
    return await _store.cleanup_old_runs(*args, **kwargs)
