"""Web-runtime-bound monitor routes that stay on the main web process."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from backend.monitor.api.http.dependencies import get_current_user_id
from backend.monitor.api.http.execution_target import resolve_monitor_evaluation_base_url
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
            execution_base_url=resolve_monitor_evaluation_base_url(request),
            token=_extract_bearer_token(request),
            schedule_task=background_tasks.add_task,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
