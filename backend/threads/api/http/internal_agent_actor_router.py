"""Internal agent-actor identity routes backed by threads-owned data."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from backend.threads import runtime_access
from backend.web.core.dependencies import get_app

router = APIRouter(prefix="/api/internal/identity", tags=["threads-internal"])


@router.get("/agent-actors/{social_user_id}/exists")
def has_agent_actor_user(
    social_user_id: str,
    app: Annotated[Any, Depends(get_app)],
) -> dict[str, Any]:
    return {"exists": runtime_access.get_agent_actor_lookup(app).is_agent_actor_user(social_user_id)}
