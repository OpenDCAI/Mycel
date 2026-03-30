"""Sandbox Monitor API - View-ready endpoints backed by monitor_service."""

from fastapi import APIRouter, HTTPException

from backend.web.services import monitor_service

router = APIRouter(prefix="/api/monitor")


@router.get("/threads")
def list_threads():
    return monitor_service.list_threads()


@router.get("/thread/{thread_id}")
def get_thread(thread_id: str):
    try:
        return monitor_service.get_thread(thread_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/leases")
def list_leases():
    return monitor_service.list_leases()


@router.get("/lease/{lease_id}")
def get_lease(lease_id: str):
    try:
        return monitor_service.get_lease(lease_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/diverged")
def list_diverged():
    return monitor_service.list_diverged()


@router.get("/events")
def list_events(limit: int = 100):
    return monitor_service.list_events(limit)


@router.get("/event/{event_id}")
def get_event(event_id: str):
    try:
        return monitor_service.get_event(event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
