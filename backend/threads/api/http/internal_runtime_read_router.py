"""Internal runtime-read routes for cross-backend thread reads."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from backend.threads import runtime_access
from backend.web.core.dependencies import get_app

router = APIRouter(prefix="/api/internal/thread-runtime", tags=["threads-internal"])


@router.get("/activities")
def list_active_threads_for_agent(
    agent_user_id: str,
    app: Annotated[Any, Depends(get_app)],
) -> list[dict[str, Any]]:
    return [asdict(activity) for activity in runtime_access.get_activity_reader(app).list_active_threads_for_agent(agent_user_id)]


@router.get("/conversations/hire")
async def list_hire_conversations_for_user(
    user_id: str,
    app: Annotated[Any, Depends(get_app)],
) -> list[dict[str, Any]]:
    return [
        asdict(item)
        for item in await runtime_access.get_conversation_reader(app).list_hire_conversations_for_user(user_id)
    ]
