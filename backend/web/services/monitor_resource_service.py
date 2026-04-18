"""Monitor resource boundary for overview and sandbox file reads."""

from __future__ import annotations

from typing import Any

from backend.web.services import resource_projection_service, resource_service
from backend.web.services.resource_cache import get_resource_overview_snapshot, refresh_resource_overview_sync


def get_monitor_resource_overview() -> dict[str, Any]:
    return get_resource_overview_snapshot()


def refresh_monitor_resource_overview() -> dict[str, Any]:
    # @@@manual-resource-refresh-must-probe - the monitor refresh button must fetch new
    # sandbox metrics first; recomputing the overview alone just re-labels stale snapshots.
    resource_service.refresh_resource_snapshots()
    return refresh_resource_overview_sync()


def browse_monitor_sandbox(sandbox_id: str, path: str) -> dict[str, Any]:
    return resource_service.browse_sandbox(sandbox_id, path)


def read_monitor_sandbox(sandbox_id: str, path: str) -> dict[str, Any]:
    return resource_service.read_sandbox(sandbox_id, path)


def list_user_resource_providers(app: Any, user_id: str) -> dict[str, Any]:
    return resource_projection_service.list_user_resource_providers(app, user_id)
