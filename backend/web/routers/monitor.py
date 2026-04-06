"""Sandbox Monitor API - thin router over monitor core."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.web.core.dependencies import get_current_user_id
from backend.web.services import monitor_service
from backend.web.services.resource_cache import (
    get_resource_overview_snapshot,
    refresh_resource_overview_sync,
)

router = APIRouter(prefix="/api/monitor")


@router.get("/threads")
def list_threads(user_id: Annotated[str, Depends(get_current_user_id)]):
    # TODO(multi-tenant): threads are stored in SQLite (sandbox DB) and linked to members via
    # chat_sessions.member_id → members.owner_user_id. Filtering requires a JOIN-capable repo
    # method. Add owner filtering once monitor_repo exposes query_threads(owner_user_id=...).
    return monitor_service.list_threads()


@router.get("/thread/{thread_id}")
def get_thread(thread_id: str, user_id: Annotated[str, Depends(get_current_user_id)]):
    return monitor_service.get_thread(thread_id)


@router.get("/leases")
def list_leases(user_id: Annotated[str, Depends(get_current_user_id)]):
    return monitor_service.list_leases()


@router.get("/lease/{lease_id}")
def get_lease(lease_id: str, user_id: Annotated[str, Depends(get_current_user_id)]):
    try:
        return monitor_service.get_lease(lease_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/diverged")
def list_diverged(user_id: Annotated[str, Depends(get_current_user_id)]):
    return monitor_service.list_diverged()


@router.get("/events")
def list_events(user_id: Annotated[str, Depends(get_current_user_id)], limit: int = 100):
    return monitor_service.list_events(limit=limit)


@router.get("/event/{event_id}")
def get_event(event_id: str, user_id: Annotated[str, Depends(get_current_user_id)]):
    try:
        return monitor_service.get_event(event_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/health")
def health_snapshot(user_id: Annotated[str, Depends(get_current_user_id)]):
    return monitor_service.runtime_health_snapshot()


@router.get("/resources")
def resources_overview(user_id: Annotated[str, Depends(get_current_user_id)]):
    return get_resource_overview_snapshot()


@router.post("/resources/refresh")
async def resources_refresh(user_id: Annotated[str, Depends(get_current_user_id)]):
    # @@@refresh-off-main-loop - provider I/O stays off event loop to avoid request head-of-line blocking.
    return await asyncio.to_thread(refresh_resource_overview_sync)


@router.get("/sandbox/{lease_id}/browse")
async def sandbox_browse(lease_id: str, user_id: Annotated[str, Depends(get_current_user_id)], path: str = Query(default="/")):
    from backend.web.services.resource_service import sandbox_browse as _browse

    try:
        return await asyncio.to_thread(_browse, lease_id, path)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.get("/sandbox/{lease_id}/read")
async def sandbox_read_file(lease_id: str, user_id: Annotated[str, Depends(get_current_user_id)], path: str = Query(...)):
    from backend.web.services.resource_service import sandbox_read as _read

    try:
        return await asyncio.to_thread(_read, lease_id, path)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
