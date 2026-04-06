"""Monitor router compatibility layer.

Expose the richer monitor implementation from ``backend.web.monitor`` while
preserving the newer resource/health helper endpoints added on main.
"""

import asyncio

from fastapi import HTTPException, Query, Request

from backend.web.monitor import get_db, list_evaluations, list_leases, router
from backend.web.services import monitor_service
from backend.web.services.resource_cache import (
    get_monitor_resource_overview_snapshot,
    refresh_monitor_resource_overview_sync,
)


@router.get("/health")
def health_snapshot():
    return monitor_service.runtime_health_snapshot()


@router.get("/dashboard")
def dashboard_snapshot(request: Request):
    health = monitor_service.runtime_health_snapshot()
    resources = get_monitor_resource_overview_snapshot()
    db_gen = get_db()
    db = next(db_gen)
    try:
        leases = list_leases(db=db)
    finally:
        db_gen.close()
    evaluations = list_evaluations(limit=5, offset=0, request=request)

    resource_summary = resources.get("summary") or {}
    lease_summary = leases.get("summary") or {}
    latest_eval = (evaluations.get("items") or [None])[0]

    latest_eval_summary = None
    if latest_eval:
        total = int(latest_eval.get("threads_total") or 0)
        done = int(latest_eval.get("threads_done") or 0)
        progress_pct = round((done / total) * 100, 1) if total > 0 else 0.0
        score = latest_eval.get("score") or {}
        latest_eval_summary = {
            "evaluation_id": latest_eval.get("evaluation_id"),
            "evaluation_url": latest_eval.get("evaluation_url"),
            "status": latest_eval.get("status"),
            "progress_pct": progress_pct,
            "threads_done": done,
            "threads_total": total,
            "publishable": bool(score.get("publishable")),
            "primary_score_pct": score.get("primary_score_pct"),
            "updated_ago": latest_eval.get("updated_ago"),
        }

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
            "evaluations_running": sum(1 for item in (evaluations.get("items") or []) if item.get("status") == "running"),
        },
        "latest_evaluation": latest_eval_summary,
    }


@router.get("/resources")
def resources_overview():
    return get_monitor_resource_overview_snapshot()


@router.post("/resources/refresh")
async def resources_refresh():
    # @@@refresh-off-main-loop - provider I/O stays off event loop to avoid request head-of-line blocking.
    return await asyncio.to_thread(refresh_monitor_resource_overview_sync)


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
