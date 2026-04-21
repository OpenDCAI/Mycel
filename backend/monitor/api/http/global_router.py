"""Global monitor routes eligible for future monitor_app mounting."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.monitor.api.http.dependencies import get_current_user_id
from backend.monitor.infrastructure.web import gateway as monitor_gateway

router = APIRouter()


class EvaluationBatchCreateRequest(BaseModel):
    agent_user_id: str
    scenario_ids: list[str] = Field(min_length=1)
    sandbox: str = "local"
    max_concurrent: int = Field(default=1, ge=1, le=50)


def _or_404(fn, *args):
    try:
        return fn(*args)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _or_404_or_503(fn, *args):
    try:
        return fn(*args)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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
    return _or_404_or_503(monitor_gateway.get_operation_detail, operation_id)


@router.get("/runtimes/{runtime_id}")
def runtime_detail_snapshot(runtime_id: str):
    return _or_404(monitor_gateway.get_runtime_detail, runtime_id)


@router.get("/sandbox-configs")
def sandbox_configs_snapshot():
    return monitor_gateway.get_sandbox_configs()


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
