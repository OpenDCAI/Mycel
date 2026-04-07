"""User-scoped resource endpoints."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.web.core.dependencies import get_current_user_id
from backend.web.services import resource_projection_service

router = APIRouter(prefix="/api/resources", tags=["resources"])


@router.get("/overview")
async def resources_overview(
    user_id: Annotated[str, Depends(get_current_user_id)],
    request: Request,
) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            resource_projection_service.list_user_resource_providers,
            request.app,
            user_id,
        )
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
