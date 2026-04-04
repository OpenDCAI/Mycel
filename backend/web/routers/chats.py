"""Chat API router — entity-to-entity communication."""

import asyncio
import json
import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.web.core.dependencies import get_app, get_current_user_id
from backend.web.utils.serializers import avatar_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chats", tags=["chats"])


class CreateChatBody(BaseModel):
    user_ids: list[str]
    title: str | None = None


class SendMessageBody(BaseModel):
    content: str
    sender_id: str
    mentioned_ids: list[str] | None = None


@router.get("")
async def list_chats(
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """List all chats for the current user (social identity from JWT)."""
    return app.state.chat_service.list_chats_for_user(user_id)


@router.post("")
async def create_chat(
    body: CreateChatBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Create a chat between users. 2 users = 1:1 chat, 3+ = group chat."""
    chat_service = app.state.chat_service
    try:
        if len(body.user_ids) >= 3:
            chat = chat_service.create_group_chat(body.user_ids, body.title)
        else:
            chat = chat_service.find_or_create_chat(body.user_ids, body.title)
        return {"id": chat.id, "title": chat.title, "status": chat.status, "created_at": chat.created_at}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{chat_id}")
async def get_chat(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Get chat details with member list."""
    chat = app.state.chat_repo.get_by_id(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    participants = app.state.chat_entity_repo.list_participants(chat_id)
    entity_repo = app.state.entity_repo
    member_repo = app.state.member_repo
    entities_info = []
    for p in participants:
        e = entity_repo.get_by_id(p.user_id)
        if e:
            m = member_repo.get_by_id(e.member_id)
            entities_info.append(
                {
                    "id": p.user_id,
                    "name": e.name,
                    "type": e.type,
                    "avatar_url": avatar_url(e.member_id, bool(m.avatar if m else None)),
                }
            )
        else:
            # Human participant — no entity row, resolve from member_repo
            m = member_repo.get_by_id(p.user_id)
            if m:
                entities_info.append(
                    {
                        "id": p.user_id,
                        "name": m.name,
                        "type": "human",
                        "avatar_url": avatar_url(m.id, bool(m.avatar)),
                    }
                )
    return {
        "id": chat.id,
        "title": chat.title,
        "status": chat.status,
        "created_at": chat.created_at,
        "entities": entities_info,
    }


@router.get("/{chat_id}/messages")
async def list_messages(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
    limit: int = Query(50, ge=1, le=200),
    before: float | None = Query(None),
):
    """List messages in a chat."""
    msgs = app.state.chat_message_repo.list_by_chat(chat_id, limit=limit, before=before)
    # Batch sender name lookup: entity_repo (agents) → member_repo (humans)
    entity_repo = app.state.entity_repo
    member_repo = app.state.member_repo
    sender_ids = {m.sender_id for m in msgs}
    sender_names: dict[str, str] = {}
    for sid in sender_ids:
        e = entity_repo.get_by_id(sid)
        if e:
            sender_names[sid] = e.name
        else:
            m = member_repo.get_by_id(sid)
            sender_names[sid] = m.name if m else "unknown"
    return [
        {
            "id": m.id,
            "chat_id": m.chat_id,
            "sender_id": m.sender_id,
            "sender_name": sender_names.get(m.sender_id, "unknown"),
            "content": m.content,
            "mentioned_ids": m.mentioned_ids,
            "created_at": m.created_at,
        }
        for m in msgs
    ]


@router.post("/{chat_id}/read")
async def mark_read(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Mark all messages in this chat as read for the current user."""
    import time

    app.state.chat_entity_repo.update_last_read(chat_id, user_id, time.time())
    return {"status": "ok"}


@router.post("/{chat_id}/messages")
async def send_message(
    chat_id: str,
    body: SendMessageBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Send a message in a chat."""
    if not body.content.strip():
        raise HTTPException(400, "Content cannot be empty")
    # Verify sender_id belongs to the authenticated user
    _verify_participant_ownership(app, body.sender_id, user_id)
    chat_service = app.state.chat_service
    msg = chat_service.send_message(chat_id, body.sender_id, body.content, body.mentioned_ids)
    return {
        "id": msg.id,
        "chat_id": msg.chat_id,
        "sender_id": msg.sender_id,
        "content": msg.content,
        "mentioned_ids": msg.mentioned_ids,
        "created_at": msg.created_at,
    }


@router.get("/{chat_id}/events")
async def stream_chat_events(
    chat_id: str,
    token: str | None = None,
    app: Annotated[Any, Depends(get_app)] = None,
):
    """SSE stream for chat events. Uses ?token= for auth."""
    from backend.web.core.dependencies import _DEV_SKIP_AUTH

    if not _DEV_SKIP_AUTH:
        if not token:
            raise HTTPException(401, "Missing token")
        try:
            app.state.auth_service.verify_token(token)
        except ValueError as e:
            raise HTTPException(401, str(e))

    event_bus = app.state.chat_event_bus
    queue = event_bus.subscribe(chat_id)

    async def event_generator():
        try:
            yield "retry: 5000\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    event_type = event.get("event", "message")
                    data = event.get("data", {})
                    yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            event_bus.unsubscribe(chat_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Contact management (block/mute)
# ---------------------------------------------------------------------------


class SetContactBody(BaseModel):
    owner_id: str
    target_id: str
    relation: Literal["normal", "blocked", "muted"]


def _verify_participant_ownership(app: Any, participant_id: str, user_id: str) -> None:
    """Raise 403 if participant_id does not belong to the authenticated user.

    For humans: participant_id == user_id (direct match).
    For agents: participant_id == member_id, and agent_member.owner_user_id == user_id.
    """
    if participant_id == user_id:
        return
    # Check if it's an agent member owned by this user
    agent_member = app.state.member_repo.get_by_id(participant_id)
    if agent_member and agent_member.owner_user_id == user_id:
        return
    raise HTTPException(403, "Participant does not belong to you")


@router.post("/contacts")
async def set_contact(
    body: SetContactBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Set a directional contact relationship (block/mute/normal)."""
    _verify_participant_ownership(app, body.owner_id, user_id)
    import time

    from storage.contracts import ContactRow

    contact_repo = app.state.contact_repo
    contact_repo.upsert(
        ContactRow(
            owner_id=body.owner_id,
            target_id=body.target_id,
            relation=body.relation,
            created_at=time.time(),
            updated_at=time.time(),
        )
    )
    return {"status": "ok", "relation": body.relation}


@router.delete("/contacts/{owner_id}/{target_id}")
async def delete_contact(
    owner_id: str,
    target_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Delete a contact relationship."""
    _verify_participant_ownership(app, owner_id, user_id)
    contact_repo = app.state.contact_repo
    contact_repo.delete(owner_id, target_id)
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Chat mute
# ---------------------------------------------------------------------------


class MuteChatBody(BaseModel):
    user_id: str
    muted: bool
    mute_until: float | None = None


@router.post("/{chat_id}/mute")
async def mute_chat(
    chat_id: str,
    body: MuteChatBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Mute/unmute a chat for the current user."""
    _verify_participant_ownership(app, body.user_id, user_id)
    chat_entity_repo = app.state.chat_entity_repo
    chat_entity_repo.update_mute(chat_id, body.user_id, body.muted, body.mute_until)
    return {"status": "ok", "muted": body.muted}


@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Delete a chat. Caller must be a participant."""
    chat = app.state.chat_repo.get_by_id(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    if not app.state.chat_entity_repo.is_participant_in_chat(chat_id, user_id):
        raise HTTPException(403, "Not a participant of this chat")
    app.state.chat_repo.delete(chat_id)
    return {"status": "deleted"}
