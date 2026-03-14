"""Sandbox Monitor API - thin router over monitor core.

All endpoints require JWT authentication. The /thread/{thread_id} endpoint
additionally verifies thread ownership via verify_thread_owner.
"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.web.core.dependencies import get_current_member_id, verify_thread_owner
from backend.web.services import monitor_service
from backend.web.services.resource_cache import (
    get_resource_overview_snapshot,
    refresh_resource_overview_sync,
)

router = APIRouter(prefix="/api/monitor")


@router.get("/threads")
def list_threads(_member_id: Annotated[str, Depends(get_current_member_id)] = ""):
    return monitor_service.list_threads()


@router.get("/thread/{thread_id}")
def get_thread(thread_id: str, _owner: Annotated[str, Depends(verify_thread_owner)] = ""):
    return monitor_service.get_thread(thread_id)


@router.get("/leases")
def list_leases(_member_id: Annotated[str, Depends(get_current_member_id)] = ""):
    return monitor_service.list_leases()


@router.get("/lease/{lease_id}")
def get_lease(lease_id: str, _member_id: Annotated[str, Depends(get_current_member_id)] = ""):
    try:
        return monitor_service.get_lease(lease_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/diverged")
def list_diverged(_member_id: Annotated[str, Depends(get_current_member_id)] = ""):
    return monitor_service.list_diverged()


@router.get("/events")
def list_events(limit: int = 100, _member_id: Annotated[str, Depends(get_current_member_id)] = ""):
    return monitor_service.list_events(limit=limit)


@router.get("/event/{event_id}")
def get_event(event_id: str, _member_id: Annotated[str, Depends(get_current_member_id)] = ""):
    try:
        return monitor_service.get_event(event_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/health")
def health_snapshot(_member_id: Annotated[str, Depends(get_current_member_id)] = ""):
    return monitor_service.runtime_health_snapshot()


@router.get("/resources")
def resources_overview(_member_id: Annotated[str, Depends(get_current_member_id)] = ""):
    return get_resource_overview_snapshot()


@router.post("/resources/refresh")
async def resources_refresh(_member_id: Annotated[str, Depends(get_current_member_id)] = ""):
    # @@@refresh-off-main-loop - provider I/O stays off event loop to avoid request head-of-line blocking.
    return await asyncio.to_thread(refresh_resource_overview_sync)


@router.get("/sandbox/{lease_id}/browse")
async def sandbox_browse(
    lease_id: str,
    path: str = Query(default="/"),
    _member_id: Annotated[str, Depends(get_current_member_id)] = "",
):
    from backend.web.services.resource_service import sandbox_browse as _browse
    try:
        return await asyncio.to_thread(_browse, lease_id, path)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.get("/sandbox/{lease_id}/read")
async def sandbox_read_file(
    lease_id: str,
    path: str = Query(...),
    _member_id: Annotated[str, Depends(get_current_member_id)] = "",
):
    from backend.web.services.resource_service import sandbox_read as _read
    try:
        return await asyncio.to_thread(_read, lease_id, path)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
