"""Product resources API separated from global monitor routes."""

import asyncio

from fastapi import APIRouter, HTTPException, Query

from backend.web.services.resource_cache import (
    get_resource_overview_snapshot,
    refresh_resource_overview_sync,
)

router = APIRouter(prefix="/api/resources", tags=["resources"])


@router.get("/overview")
def resources_overview():
    return get_resource_overview_snapshot()


@router.post("/overview/refresh")
async def resources_refresh():
    # @@@resource-refresh-off-main-loop - provider I/O stays off event loop for product refreshes too.
    return await asyncio.to_thread(refresh_resource_overview_sync)


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
