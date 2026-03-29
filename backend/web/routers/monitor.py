"""Monitor router compatibility layer.

Expose the richer monitor implementation from ``backend.web.monitor`` while
preserving the newer resource/health helper endpoints added on main.
"""

import asyncio

from fastapi import HTTPException, Query

from backend.web.monitor import router
from backend.web.services import monitor_service
from backend.web.services.resource_cache import (
    get_monitor_resource_overview_snapshot,
    refresh_monitor_resource_overview_sync,
)


@router.get("/health")
def health_snapshot():
    return monitor_service.runtime_health_snapshot()


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
