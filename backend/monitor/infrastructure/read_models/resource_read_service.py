from __future__ import annotations

from collections.abc import Callable
from typing import Any

from storage.runtime import build_sandbox_monitor_repo as make_sandbox_monitor_repo
from storage.runtime import list_resource_snapshots_by_sandbox


def with_resource_monitor_repo[T](callback: Callable[[Any], T]) -> T:
    repo = make_sandbox_monitor_repo()
    try:
        return callback(repo)
    finally:
        repo.close()


def snapshot_by_sandbox(resource_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return list_resource_snapshots_by_sandbox(resource_rows)
