"""Monitor router."""

import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.web.services import monitor_service, resource_service
from backend.web.services.resource_cache import (
    get_monitor_resource_overview_snapshot,
    refresh_monitor_resource_overview_sync,
)

router = APIRouter(prefix="/api/monitor")


class ResourceCleanupRequest(BaseModel):
    action: str = Field(default="cleanup_residue")
    lease_ids: list[str]
    expected_category: str


def _refresh_monitor_resources_sync():
    # @@@manual-resource-refresh-must-probe - the operator-facing refresh button must fetch new
    # sandbox metrics first; recomputing the overview alone just re-labels stale snapshots.
    resource_service.refresh_resource_snapshots()
    return refresh_monitor_resource_overview_sync()


@router.get("/health")
def health_snapshot():
    return monitor_service.runtime_health_snapshot()

@router.get("/leases")
def leases_snapshot():
    return monitor_service.list_leases()


@router.get("/dashboard")
def dashboard_snapshot():
    health = monitor_service.runtime_health_snapshot()
    resources = get_monitor_resource_overview_snapshot()
    leases = monitor_service.list_leases()
    evaluation = monitor_service.get_monitor_evaluation_dashboard_summary()

    resource_summary = resources.get("summary") or {}
    lease_summary = leases.get("summary") or {}

    return {
        "snapshot_at": health.get("snapshot_at"),
        "resources_summary": resource_summary,
        "infra": {
            "providers_active": int(resource_summary.get("active_providers") or 0),
            "providers_unavailable": int(resource_summary.get("unavailable_providers") or 0),
            "leases_total": int(lease_summary.get("total") or leases.get("count") or 0),
            "leases_diverged": int(lease_summary.get("diverged") or 0) + int(lease_summary.get("orphan_diverged") or 0),
            "leases_orphan": int(lease_summary.get("orphan") or 0) + int(lease_summary.get("orphan_diverged") or 0),
            "leases_healthy": int(lease_summary.get("healthy") or 0),
        },
        "workload": {
            "db_sessions_total": int(((health.get("db") or {}).get("counts") or {}).get("chat_sessions") or 0),
            "provider_sessions_total": int(((health.get("sessions") or {}).get("total")) or 0),
            "running_sessions": int(resource_summary.get("running_sessions") or 0),
            "evaluations_running": int(evaluation["evaluations_running"]),
        },
        "latest_evaluation": evaluation["latest_evaluation"],
    }


@router.get("/evaluation")
def evaluation_snapshot():
    return monitor_service.get_monitor_evaluation_truth()


@router.get("/resources")
def resources_overview():
    return get_monitor_resource_overview_snapshot()


@router.post("/resources/refresh")
async def resources_refresh():
    # @@@refresh-off-main-loop - provider I/O stays off event loop to avoid request head-of-line blocking.
    return await asyncio.to_thread(_refresh_monitor_resources_sync)


@router.post("/resources/cleanup")
async def resources_cleanup(payload: ResourceCleanupRequest):
    from backend.web.services import monitor_service

    try:
        return await asyncio.to_thread(
            monitor_service.cleanup_resource_leases,
            action=payload.action,
            lease_ids=payload.lease_ids,
            expected_category=payload.expected_category,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/sandbox/{lease_id}/browse")
async def sandbox_browse(lease_id: str, path: str = Query(default="/")):
    from backend.web.services.resource_service import sandbox_browse as _browse

    try:
        return await asyncio.to_thread(_browse, lease_id, path)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.get("/sandbox/{lease_id}/read")
async def sandbox_read_file(lease_id: str, path: str = Query(...)):
    from backend.web.services.resource_service import sandbox_read as _read

    try:
        return await asyncio.to_thread(_read, lease_id, path)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
