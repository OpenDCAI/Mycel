"""Sandbox Monitor API - thin router over monitor core."""

import asyncio

from fastapi import APIRouter, HTTPException

from backend.web.monitor_core import diagnose, observe
from backend.web.monitor_core.resource_overview_cache import (
    get_resource_overview_snapshot,
    refresh_resource_overview_sync,
)

router = APIRouter(prefix="/api/monitor")


@router.get("/threads")
def list_threads():
    return observe.list_threads()


@router.get("/thread/{thread_id}")
def get_thread(thread_id: str):
    return observe.get_thread(thread_id)


@router.get("/leases")
def list_leases():
    return observe.list_leases()


@router.get("/lease/{lease_id}")
def get_lease(lease_id: str):
    try:
        return observe.get_lease(lease_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/diverged")
def list_diverged():
    return observe.list_diverged()


@router.get("/events")
def list_events(limit: int = 100):
    return observe.list_events(limit=limit)


@router.get("/event/{event_id}")
def get_event(event_id: str):
    try:
        return observe.get_event(event_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/health")
def health_snapshot():
    return diagnose.runtime_health_snapshot()


@router.get("/resources")
def resources_overview():
    return get_resource_overview_snapshot()


@router.post("/resources/refresh")
async def resources_refresh():
    # @@@refresh-off-main-loop - provider I/O stays off event loop to avoid request head-of-line blocking.
    return await asyncio.to_thread(refresh_resource_overview_sync)
