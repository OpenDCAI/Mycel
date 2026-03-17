"""Entity & Member endpoints — new entity-chat system."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from backend.web.core.dependencies import get_app, get_current_member_id

router = APIRouter(prefix="/api/entities", tags=["entities"])

# ---------------------------------------------------------------------------
# Members (agent directory)
# ---------------------------------------------------------------------------

members_router = APIRouter(prefix="/api/members", tags=["members"])


@members_router.get("")
async def list_members(
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """List all agent members (templates). For member directory page."""
    member_repo = app.state.member_repo

    all_members = member_repo.list_all()
    result = []
    for m in all_members:
        if m.type != "mycel_agent":
            continue
        owner = member_repo.get_by_id(m.owner_id) if m.owner_id else None
        result.append({
            "id": m.id,
            "name": m.name,
            "type": m.type,
            "avatar": m.avatar,
            "description": m.description,
            "owner_name": owner.name if owner else None,
            "is_mine": m.owner_id == member_id,
            "created_at": m.created_at,
        })
    return result


@router.get("")
async def list_entities(
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """List all entities (social identities) for discovery. Used by New Chat entity picker.
    Entity = Thread's social identity. This lists all entities so users can find who to chat with."""
    entity_repo = app.state.entity_repo
    all_entities = entity_repo.list_all()
    return [
        {"id": e.id, "name": e.name, "type": e.type, "avatar": getattr(e, "avatar", None)}
        for e in all_entities
    ]


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
