"""Sandbox management endpoints."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.web.core.dependencies import get_current_user_id
from backend.web.services import sandbox_service

router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])


def _runtime_http_error(exc: RuntimeError) -> HTTPException:
    message = str(exc)
    status = 404 if "not found" in message.lower() else 409
    return HTTPException(status, message)


async def _mutate_runtime_action(runtime_id: str, action: str, provider: str | None) -> dict[str, Any]:
    try:
        result = await asyncio.to_thread(
            sandbox_service.mutate_sandbox_runtime,
            runtime_id=runtime_id,
            action=action,
            provider_hint=provider,
        )
        return _public_runtime_payload(result)
    except RuntimeError as e:
        raise _runtime_http_error(e) from e


def _public_runtime_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "lease_id"}


@router.get("/types")
async def list_sandbox_types() -> dict[str, Any]:
    """List available sandbox types."""
    types = await asyncio.to_thread(sandbox_service.available_sandbox_types)
    return {"types": types}


@router.get("/runtimes")
async def list_sandbox_runtimes() -> dict[str, Any]:
    """List all sandbox runtime rows across providers."""
    _, managers = await asyncio.to_thread(sandbox_service.init_providers_and_managers)
    runtime_rows = await asyncio.to_thread(sandbox_service.load_all_sandbox_runtimes, managers)
    return {"runtime_rows": [_public_runtime_payload(row) for row in runtime_rows]}


@router.get("/sandboxes/mine")
async def list_my_sandboxes(
    user_id: Annotated[str, Depends(get_current_user_id)],
    request: Request,
) -> dict[str, Any]:
    thread_repo = getattr(request.app.state, "thread_repo", None)
    user_repo = getattr(request.app.state, "user_repo", None)
    sandboxes = await asyncio.to_thread(
        sandbox_service.list_user_sandboxes,
        user_id,
        thread_repo=thread_repo,
        user_repo=user_repo,
    )
    return {"sandboxes": sandboxes}


@router.get("/runtimes/{runtime_id}/metrics")
async def get_sandbox_runtime_metrics(runtime_id: str, provider: str | None = Query(default=None)) -> dict[str, Any]:
    """Get metrics for a specific sandbox runtime row."""
    try:
        return await asyncio.to_thread(sandbox_service.get_runtime_metrics, runtime_id, provider)
    except RuntimeError as e:
        raise _runtime_http_error(e) from e


@router.post("/runtimes/{runtime_id}/pause")
async def pause_sandbox_runtime(runtime_id: str, provider: str | None = Query(default=None)) -> dict[str, Any]:
    """Pause a sandbox runtime row."""
    return await _mutate_runtime_action(runtime_id, "pause", provider)


@router.post("/runtimes/{runtime_id}/resume")
async def resume_sandbox_runtime(runtime_id: str, provider: str | None = Query(default=None)) -> dict[str, Any]:
    """Resume a paused sandbox runtime row."""
    return await _mutate_runtime_action(runtime_id, "resume", provider)


@router.delete("/runtimes/{runtime_id}")
async def destroy_sandbox_runtime(runtime_id: str, provider: str | None = Query(default=None)) -> dict[str, Any]:
    """Destroy a sandbox runtime row."""
    return await _mutate_runtime_action(runtime_id, "destroy", provider)
