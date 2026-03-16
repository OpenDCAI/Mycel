"""Entity endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from backend.web.core.dependencies import get_app, get_current_member_id

router = APIRouter(prefix="/api/entities", tags=["entities"])


@router.get("/{entity_id}/agent-thread")
async def get_agent_thread(
    entity_id: str,
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Get the thread_id for an agent entity."""
    entity = app.state.entity_repo.get_by_id(entity_id)
    if not entity:
        raise HTTPException(404, "Entity not found")
    if entity.type != "agent" or not entity.thread_id:
        raise HTTPException(400, "Entity is not an agent or has no thread")
    return {"entity_id": entity_id, "thread_id": entity.thread_id}
