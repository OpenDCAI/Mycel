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
    """Get the thread_id for an entity's agent. Accepts human or agent entity."""
    entity = app.state.entity_repo.get_by_id(entity_id)
    if not entity:
        raise HTTPException(404, "Entity not found")
    # If this is already an agent with a thread, return directly
    if entity.type == "agent" and entity.thread_id:
        return {"entity_id": entity_id, "thread_id": entity.thread_id}
    # If this is a human entity, find the agent entity owned by the same member
    member = app.state.member_repo.get_by_id(entity.member_id)
    if member:
        # Find agent members owned by this member
        agents = app.state.member_repo.list_by_owner(member.id)
        for agent_member in agents:
            agent_entities = app.state.entity_repo.get_by_member_id(agent_member.id)
            for ae in agent_entities:
                if ae.type == "agent" and ae.thread_id:
                    return {"entity_id": ae.id, "thread_id": ae.thread_id}
    raise HTTPException(404, "No agent thread found for this entity")
