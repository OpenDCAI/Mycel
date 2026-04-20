"""Web-runtime-bound monitor routes that stay on the main web process."""

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.monitor.api.http.dependencies import get_app, get_current_user_id
from backend.monitor.infrastructure.web import gateway as monitor_gateway

router = APIRouter()


class EvaluationBatchCreateRequest(BaseModel):
    agent_user_id: str
    scenario_ids: list[str] = Field(min_length=1)
    sandbox: str = "local"
    max_concurrent: int = Field(default=1, ge=1, le=50)


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


@router.post("/evaluation/batches")
def evaluation_batch_create_action(
    payload: EvaluationBatchCreateRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    return monitor_gateway.create_evaluation_batch(
        submitted_by_user_id=user_id,
        agent_user_id=payload.agent_user_id,
        scenario_ids=payload.scenario_ids,
        sandbox=payload.sandbox,
        max_concurrent=payload.max_concurrent,
    )


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
