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


async def _mutate_session_action(session_id: str, action: str, provider: str | None) -> dict[str, Any]:
    try:
        result = await asyncio.to_thread(
            sandbox_service.mutate_sandbox_session,
            session_id=session_id,
            action=action,
            provider_hint=provider,
        )
        return _public_session_payload(result)
    except RuntimeError as e:
        raise _runtime_http_error(e) from e


def _public_session_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "lease_id"}


@router.get("/types")
async def list_sandbox_types() -> dict[str, Any]:
    """List available sandbox types."""
    types = await asyncio.to_thread(sandbox_service.available_sandbox_types)
    return {"types": types}


@router.get("/sessions")
async def list_sandbox_sessions() -> dict[str, Any]:
    """List all sandbox sessions across providers."""
    _, managers = await asyncio.to_thread(sandbox_service.init_providers_and_managers)
    sessions = await asyncio.to_thread(sandbox_service.load_all_sessions, managers)
    return {"sessions": [_public_session_payload(session) for session in sessions]}


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


@router.get("/sessions/{session_id}/metrics")
async def get_session_metrics(session_id: str, provider: str | None = Query(default=None)) -> dict[str, Any]:
    """Get metrics for a specific sandbox session."""
    try:
        return await asyncio.to_thread(sandbox_service.get_session_metrics, session_id, provider)
    except RuntimeError as e:
        raise _runtime_http_error(e) from e


@router.post("/sessions/{session_id}/pause")
async def pause_sandbox_session(session_id: str, provider: str | None = Query(default=None)) -> dict[str, Any]:
    """Pause a sandbox session."""
    return await _mutate_session_action(session_id, "pause", provider)


@router.post("/sessions/{session_id}/resume")
async def resume_sandbox_session(session_id: str, provider: str | None = Query(default=None)) -> dict[str, Any]:
    """Resume a paused sandbox session."""
    return await _mutate_session_action(session_id, "resume", provider)


@router.delete("/sessions/{session_id}")
async def destroy_sandbox_session(session_id: str, provider: str | None = Query(default=None)) -> dict[str, Any]:
    """Destroy a sandbox session."""
    return await _mutate_session_action(session_id, "destroy", provider)
