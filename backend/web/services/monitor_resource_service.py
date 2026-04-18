"""Monitor resource boundary for overview and sandbox file reads."""

from __future__ import annotations

from typing import Any

from backend.web.services import monitor_resource_io_service, monitor_sandbox_projection_service, resource_projection_service
from backend.web.services.resource_cache import get_resource_overview_snapshot, refresh_resource_overview_sync


def _attach_monitor_triage(payload: dict[str, Any]) -> dict[str, Any]:
    sandbox_payload = monitor_sandbox_projection_service.list_monitor_sandboxes()
    payload["triage"] = sandbox_payload.get("triage") or {"summary": {}, "groups": []}
    return payload


def get_monitor_resource_overview() -> dict[str, Any]:
    return _attach_monitor_triage(get_resource_overview_snapshot())


def refresh_monitor_resource_overview() -> dict[str, Any]:
    # @@@manual-resource-refresh-must-probe - the monitor refresh button must fetch new
    # sandbox metrics first; recomputing the overview alone just re-labels stale snapshots.
    monitor_resource_io_service.refresh_resource_snapshots()
    return _attach_monitor_triage(refresh_resource_overview_sync())


def browse_monitor_sandbox(sandbox_id: str, path: str) -> dict[str, Any]:
    return monitor_resource_io_service.browse_sandbox(sandbox_id, path)


def read_monitor_sandbox(sandbox_id: str, path: str) -> dict[str, Any]:
    return monitor_resource_io_service.read_sandbox(sandbox_id, path)


def list_user_resource_providers(app: Any, user_id: str) -> dict[str, Any]:
    return resource_projection_service.list_user_resource_providers(app, user_id)
