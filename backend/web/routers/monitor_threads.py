"""Web-owned monitor-local thread routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.monitor.api.http.dependencies import get_app, get_current_user_id
from backend.monitor.infrastructure.web import gateway as monitor_gateway

router = APIRouter()


@router.get("/threads")
def threads_snapshot(
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)] = None,
):
    return monitor_gateway.list_threads(app, user_id)


@router.get("/threads/{thread_id}")
async def thread_detail_snapshot(request: Request, thread_id: str):
    try:
        return await monitor_gateway.get_thread_detail(request.app, thread_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
