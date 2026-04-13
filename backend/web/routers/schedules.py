"""Agent schedule runtime API."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.web.core.dependencies import get_current_user_id
from backend.web.services import schedule_runtime_service

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


@router.post("/{schedule_id}/run")
async def run_schedule(
    schedule_id: str,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    try:
        item = await schedule_runtime_service.trigger_schedule(request.app, schedule_id, owner_user_id=user_id, triggered_by="manual")
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message else 400
        raise HTTPException(status_code, message) from exc
    return {"item": item}
