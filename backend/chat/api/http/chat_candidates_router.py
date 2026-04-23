"""Chat candidate API router — chat/backend owner module."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from backend.chat.api.http.dependencies import (
    get_contact_repo,
    get_current_user_id,
    get_relationship_service,
    get_user_directory,
)
from backend.identity.avatar.urls import avatar_url
from messaging.social_access import active_contact_target_ids, can_chat_with_owner_scope
from storage.contracts import UserType

router = APIRouter(prefix="/api/users", tags=["users"])


def _relationship_states_for_user(relationship_service: Any, user_id: str) -> dict[str, str]:
    if relationship_service is None:
        raise HTTPException(503, "chat bootstrap not attached: relationship_service")
    states: dict[str, str] = {}
    for row in relationship_service.list_for_user(user_id):
        other_id = getattr(row, "other_user_id", None)
        if other_id is None:
            user_low = getattr(row, "user_low")
            user_high = getattr(row, "user_high")
            other_id = user_high if user_id == user_low else user_low
        states[str(other_id)] = str(getattr(row, "state"))
    return states


@router.get("/chat-candidates")
async def list_chat_candidates(
    user_id: Annotated[str, Depends(get_current_user_id)],
    user_directory: Annotated[Any, Depends(get_user_directory)],
    relationship_service: Annotated[Any, Depends(get_relationship_service)],
    contact_repo: Annotated[Any, Depends(get_contact_repo)],
):
    users = user_directory.list_all()
    user_map = {user.id: user for user in users}
    relationship_states = _relationship_states_for_user(relationship_service, user_id)
    try:
        if contact_repo is None:
            raise RuntimeError("chat bootstrap not attached: contact_repo")
        contact_targets = active_contact_target_ids(contact_repo, user_id)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc

    items = []
    for user in users:
        if user.id == user_id:
            continue
        is_owned = user.type is UserType.AGENT and user.owner_user_id == user_id
        relationship_state = relationship_states.get(user.id, "none")
        owner_user_id = str(user.owner_user_id) if user.type is UserType.AGENT and user.owner_user_id else None
        can_chat = can_chat_with_owner_scope(
            is_owned=is_owned,
            relationship_state=relationship_state,
            has_contact=user.id in contact_targets,
            owner_relationship_state=relationship_states.get(owner_user_id, "none") if owner_user_id else None,
            owner_has_contact=owner_user_id in contact_targets if owner_user_id else False,
        )
        if user.type is UserType.HUMAN:
            items.append(
                {
                    "user_id": user.id,
                    "name": user.display_name,
                    "type": "human",
                    "avatar_url": avatar_url(user.id, bool(user.avatar)),
                    "owner_name": None,
                    "agent_name": user.display_name,
                    "is_owned": False,
                    "relationship_state": relationship_state,
                    "can_chat": can_chat,
                }
            )
            continue

        owner = user_map.get(user.owner_user_id) if user.owner_user_id else None
        item = {
            "user_id": user.id,
            "name": user.display_name,
            "type": user.type.value,
            "avatar_url": avatar_url(user.id, bool(user.avatar)),
            "owner_name": owner.display_name if owner else None,
            "agent_name": user.display_name,
            "is_owned": is_owned,
            "relationship_state": relationship_state,
            "can_chat": can_chat,
        }
        items.append(item)
    return items
