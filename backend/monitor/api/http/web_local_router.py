"""Web-runtime-bound monitor routes that stay on the main web process."""

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from backend.monitor.api.http.dependencies import get_app, get_current_user_id
from backend.monitor.infrastructure.web import gateway as monitor_gateway

router = APIRouter()


def _extract_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    return token


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


@router.post("/evaluation/batches/{batch_id}/start")
def evaluation_batch_start_action(
    batch_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    _user_id: Annotated[str, Depends(get_current_user_id)],
):
    try:
        return monitor_gateway.start_evaluation_batch(
            batch_id=batch_id,
            base_url=str(request.base_url).rstrip("/"),
            token=_extract_bearer_token(request),
            schedule_task=background_tasks.add_task,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
