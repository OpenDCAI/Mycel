"""Monitor router."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.web.core.dependencies import get_app, get_current_user_id
from backend.web.services import monitor_service, resource_service
from backend.web.services.resource_cache import (
    get_resource_overview_snapshot,
    refresh_resource_overview_sync,
)

router = APIRouter(prefix="/api/monitor")


def _refresh_monitor_resources_sync():
    # @@@manual-resource-refresh-must-probe - the operator-facing refresh button must fetch new
    # sandbox metrics first; recomputing the overview alone just re-labels stale snapshots.
    resource_service.refresh_resource_snapshots()
    return refresh_resource_overview_sync()


@router.get("/leases")
def leases_snapshot():
    return monitor_service.list_leases()


@router.get("/threads")
def threads_snapshot(
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)] = None,
):
    return monitor_service.list_monitor_threads(app, user_id)


@router.get("/providers/{provider_id}")
def provider_detail_snapshot(provider_id: str):
    try:
        return monitor_service.get_monitor_provider_detail(provider_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/leases/{lease_id}")
def lease_detail_snapshot(lease_id: str):
    try:
        return monitor_service.get_monitor_lease_detail(lease_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/leases/{lease_id}/cleanup")
def lease_cleanup_action(lease_id: str):
    try:
        return monitor_service.request_monitor_lease_cleanup(lease_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/operations/{operation_id}")
def operation_detail_snapshot(operation_id: str):
    try:
        return monitor_service.get_monitor_operation_detail(operation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runtimes/{runtime_session_id}")
def runtime_detail_snapshot(runtime_session_id: str):
    try:
        return monitor_service.get_monitor_runtime_detail(runtime_session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/threads/{thread_id}")
async def thread_detail_snapshot(request: Request, thread_id: str):
    try:
        return await monitor_service.get_monitor_thread_detail(request.app, thread_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/dashboard")
def dashboard_snapshot():
    resources = get_resource_overview_snapshot()
    leases = monitor_service.list_leases()
    evaluation = monitor_service.build_monitor_evaluation_dashboard_summary(monitor_service.get_monitor_evaluation_truth())

    resource_summary = resources.get("summary") or {}
    lease_summary = leases.get("summary") or {}

    return {
        "snapshot_at": resource_summary.get("snapshot_at"),
        "infra": {
            "providers_active": int(resource_summary.get("active_providers") or 0),
            "providers_unavailable": int(resource_summary.get("unavailable_providers") or 0),
            "leases_total": int(lease_summary.get("total") or leases.get("count") or 0),
            "leases_diverged": int(lease_summary.get("diverged") or 0) + int(lease_summary.get("orphan_diverged") or 0),
            "leases_orphan": int(lease_summary.get("orphan") or 0) + int(lease_summary.get("orphan_diverged") or 0),
        },
        "workload": {
            "running_sessions": int(resource_summary.get("running_sessions") or 0),
            "evaluations_running": int(evaluation["evaluations_running"]),
        },
        "latest_evaluation": evaluation["latest_evaluation"],
    }


@router.get("/evaluation")
def evaluation_snapshot():
    return monitor_service.get_monitor_evaluation_workbench()


@router.get("/evaluation/batches")
def evaluation_batches_snapshot(limit: int = Query(default=50, ge=1, le=200)):
    return monitor_service.get_monitor_evaluation_batches(limit=limit)


@router.get("/evaluation/batches/{batch_id}")
def evaluation_batch_detail_snapshot(batch_id: str):
    try:
        return monitor_service.get_monitor_evaluation_batch_detail(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/evaluation/runs/{run_id}")
def evaluation_run_detail_snapshot(run_id: str):
    try:
        return monitor_service.get_monitor_evaluation_run_detail(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/resources")
def resources_overview():
    return get_resource_overview_snapshot()


@router.post("/resources/refresh")
async def resources_refresh():
    # @@@refresh-off-main-loop - provider I/O stays off event loop to avoid request head-of-line blocking.
    return await asyncio.to_thread(_refresh_monitor_resources_sync)


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
