"""Shared runtime read helpers for sandbox resource projections."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.monitor.infrastructure.read_models import resource_read_service


def query_runtime_ids(repo: Any, sandbox_ids: list[str]) -> dict[str, str | None]:
    ordered_ids = []
    seen: set[str] = set()
    for sandbox_id in sandbox_ids:
        normalized = str(sandbox_id or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered_ids.append(normalized)
    if not ordered_ids:
        return {}

    return repo.query_sandbox_instance_ids(ordered_ids)


def load_runtime_ids(sandbox_ids: list[str]) -> dict[str, str | None]:
    return resource_read_service.with_resource_monitor_repo(lambda repo: query_runtime_ids(repo, sandbox_ids))


def load_visible_resource_runtime(
    project_resource_rows: Callable[[Any, list[dict[str, Any]]], list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, str | None], dict[str, dict[str, Any]]]:
    def _load(repo: Any) -> tuple[list[dict[str, Any]], dict[str, str | None]]:
        resource_rows = project_resource_rows(repo, repo.query_resource_rows())
        runtime_ids = query_runtime_ids(repo, [str(resource_row.get("sandbox_id") or "") for resource_row in resource_rows])
        return resource_rows, runtime_ids

    resource_rows, runtime_ids = resource_read_service.with_resource_monitor_repo(_load)
    snapshot_by_sandbox = resource_read_service.snapshot_by_sandbox(resource_rows)
    return resource_rows, runtime_ids, snapshot_by_sandbox
