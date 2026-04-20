"""Shared run-event read transport helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from storage.contracts import RunEventRepo
from storage.runtime import build_storage_container

_default_run_event_repo: RunEventRepo | None = None


@dataclass(frozen=True)
class RunEventReadTransport:
    latest_run_id: Any
    list_events: Any


def _resolve_run_event_repo(run_event_repo: RunEventRepo | None) -> RunEventRepo:
    if run_event_repo is not None:
        return run_event_repo

    global _default_run_event_repo
    if _default_run_event_repo is not None:
        return _default_run_event_repo

    container = build_storage_container()
    _default_run_event_repo = container.run_event_repo()
    return _default_run_event_repo


def build_run_event_read_transport(run_event_repo: RunEventRepo | None = None) -> RunEventReadTransport:
    repo = _resolve_run_event_repo(run_event_repo)
    return RunEventReadTransport(
        latest_run_id=lambda thread_id: repo.latest_run_id(thread_id),
        list_events=lambda thread_id, run_id, *, after=0, limit=1000: repo.list_events(
            thread_id,
            run_id,
            after=after,
            limit=limit,
        ),
    )
