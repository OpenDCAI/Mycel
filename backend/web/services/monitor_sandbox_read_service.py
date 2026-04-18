"""Sandbox runtime read-source boundary for Monitor."""

from __future__ import annotations

from typing import Any

from storage.runtime import build_sandbox_monitor_repo as make_sandbox_monitor_repo


def list_sandbox_rows() -> list[dict[str, Any]]:
    repo = make_sandbox_monitor_repo()
    try:
        return repo.query_sandboxes()
    finally:
        repo.close()
