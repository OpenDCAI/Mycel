"""Monitor router."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.monitor.api.http.dependencies import get_app, get_current_user_id
from backend.monitor.infrastructure.web import gateway as monitor_gateway

router = APIRouter(prefix="/api/monitor")


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


def _or_404(fn, *args):
    try:
        return fn(*args)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _resource_io(fn, *args):
    try:
        return await asyncio.to_thread(fn, *args)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/sandboxes")
def sandboxes_snapshot():
    return monitor_gateway.list_sandboxes()


@router.get("/provider-orphan-runtimes")
def provider_orphan_runtimes_snapshot():
    return monitor_gateway.list_provider_orphan_runtimes()


@router.get("/threads")
def threads_snapshot(
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)] = None,
):
    return monitor_gateway.list_threads(app, user_id)


@router.get("/providers/{provider_id}")
def provider_detail_snapshot(provider_id: str):
    return _or_404(monitor_gateway.get_provider_detail, provider_id)


@router.get("/sandboxes/{sandbox_id}")
def sandbox_detail_snapshot(sandbox_id: str):
    return _or_404(monitor_gateway.get_sandbox_detail, sandbox_id)


@router.post("/sandboxes/{sandbox_id}/cleanup")
def sandbox_cleanup_action(sandbox_id: str):
    return _or_404(monitor_gateway.request_sandbox_cleanup, sandbox_id)


@router.post("/provider-orphan-runtimes/{provider_id}/{runtime_id}/cleanup")
def provider_orphan_runtime_cleanup_action(provider_id: str, runtime_id: str):
    return monitor_gateway.request_provider_orphan_runtime_cleanup(provider_id, runtime_id)


@router.get("/operations/{operation_id}")
def operation_detail_snapshot(operation_id: str):
    return _or_404(monitor_gateway.get_operation_detail, operation_id)


@router.get("/runtimes/{runtime_id}")
def runtime_detail_snapshot(runtime_id: str):
    return _or_404(monitor_gateway.get_runtime_detail, runtime_id)


@router.get("/sandbox-configs")
def sandbox_configs_snapshot():
    return monitor_gateway.get_sandbox_configs()


@router.get("/threads/{thread_id}")
async def thread_detail_snapshot(request: Request, thread_id: str):
    try:
        return await monitor_gateway.get_thread_detail(request.app, thread_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/dashboard")
def dashboard_snapshot():
    return monitor_gateway.get_dashboard()


@router.get("/evaluation")
def evaluation_snapshot():
    return monitor_gateway.get_evaluation_workbench()


@router.get("/evaluation/batches")
def evaluation_batches_snapshot(limit: int = Query(default=50, ge=1, le=200)):
    return monitor_gateway.get_evaluation_batches(limit=limit)


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


@router.get("/evaluation/scenarios")
def evaluation_scenarios_snapshot():
    return monitor_gateway.get_evaluation_scenarios()


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


@router.get("/evaluation/batches/{batch_id}")
def evaluation_batch_detail_snapshot(batch_id: str):
    return _or_404(monitor_gateway.get_evaluation_batch_detail, batch_id)


@router.get("/evaluation/runs/{run_id}")
def evaluation_run_detail_snapshot(run_id: str):
    return _or_404(monitor_gateway.get_evaluation_run_detail, run_id)


@router.get("/resources")
def resources_overview():
    return monitor_gateway.get_resource_overview()


@router.post("/resources/refresh")
async def resources_refresh():
    # @@@refresh-off-main-loop - provider I/O stays off event loop to avoid request head-of-line blocking.
    return await asyncio.to_thread(monitor_gateway.refresh_resource_overview)


@router.get("/sandboxes/{sandbox_id}/browse")
async def sandbox_browse(sandbox_id: str, path: str = Query(default="/")):
    return await _resource_io(monitor_gateway.browse_sandbox, sandbox_id, path)


@router.get("/sandboxes/{sandbox_id}/read")
async def sandbox_read_file(sandbox_id: str, path: str = Query(...)):
    return await _resource_io(monitor_gateway.read_sandbox, sandbox_id, path)
