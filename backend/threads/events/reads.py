"""Shared run-event read transport helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from storage.contracts import RunEventRepo

_default_run_event_repo: RunEventRepo | None = None


@dataclass(frozen=True)
class RunEventReadTransport:
    latest_run_id: Any
    list_events: Any
