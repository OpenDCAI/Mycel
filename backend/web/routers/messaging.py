"""Messaging API router — replaces chats.py.

All operations go through MessagingService (Supabase-backed).
No legacy fallback.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.web.core.dependencies import get_app, get_current_user_id
from backend.web.utils.serializers import avatar_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chats", tags=["chats"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateChatBody(BaseModel):
    user_ids: list[str]
    title: str | None = None


class SendMessageBody(BaseModel):
    content: str
    sender_id: str
    mentioned_ids: list[str] | None = None
    message_type: str = "human"
    signal: str | None = None


class MuteChatBody(BaseModel):
    user_id: str
    muted: bool
    mute_until: float | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _messaging(app: Any):
    svc = getattr(app.state, "messaging_service", None)
    if svc is None:
        raise HTTPException(503, "MessagingService not initialized")
    return svc


def _verify_member_ownership(app: Any, member_id: str, user_id: str) -> None:
    member = app.state.member_repo.get_by_id(member_id)
    if not member:
        raise HTTPException(403, "Member not found")
    if member.id == user_id:
        return  # human member sending as themselves
    if member.owner_user_id == user_id:
        return  # agent owned by current user
    raise HTTPException(403, "Member does not belong to you")


def _msg_response(m: dict[str, Any], member_repo: Any) -> dict[str, Any]:
    sender = member_repo.get_by_id(m.get("sender_id", ""))
    return {
        "id": m["id"],
        "chat_id": m["chat_id"],
        "sender_id": m.get("sender_id"),
        "sender_name": sender.name if sender else "unknown",
        "content": m["content"],
        "message_type": m.get("message_type", "human"),
        "mentioned_ids": m.get("mentioned_ids") or m.get("mentions") or [],
        "signal": m.get("signal"),
        "retracted_at": m.get("retracted_at"),
        "created_at": m.get("created_at"),
    }


# ---------------------------------------------------------------------------
# Chat list / create
# ---------------------------------------------------------------------------


@router.get("")
async def list_chats(
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    return _messaging(app).list_chats_for_user(user_id)


@router.post("")
async def create_chat(
    body: CreateChatBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    try:
        if len(body.user_ids) >= 3:
            chat = _messaging(app).create_group_chat(body.user_ids, body.title)
        else:
            chat = _messaging(app).find_or_create_chat(body.user_ids, body.title)
        return {
            "id": chat["id"],
            "title": chat.get("title"),
            "status": chat.get("status"),
            "created_at": chat.get("created_at"),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------------------
# Chat detail
# ---------------------------------------------------------------------------


@router.get("/{chat_id}")
async def get_chat(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    chat = app.state.chat_repo.get_by_id(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    if not _messaging(app).is_chat_member(chat_id, user_id):
        raise HTTPException(403, "Not a participant of this chat")
    members_list = _messaging(app).list_chat_members(chat_id)
    members_info = []
    for m in members_list:
        uid = m.get("user_id")
        if not uid:
            continue
        mem = app.state.member_repo.get_by_id(uid)
        if mem:
            members_info.append(
                {
                    "id": mem.id,
                    "name": mem.name,
                    "type": mem.type.value if hasattr(mem.type, "value") else str(mem.type),
                    "avatar_url": avatar_url(mem.id, bool(mem.avatar)),
                }
            )
    return {
        "id": chat.id,
        "title": chat.title,
        "status": chat.status,
        "created_at": chat.created_at,
        "entities": members_info,
    }


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


@router.get("/{chat_id}/messages")
async def list_messages(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
    limit: int = Query(50, ge=1, le=200),
    before: str | None = Query(None),
):
    if not _messaging(app).is_chat_member(chat_id, user_id):
        raise HTTPException(403, "Not a participant of this chat")
    msgs = _messaging(app).list_messages(chat_id, limit=limit, before=before, viewer_id=user_id)
    return [_msg_response(m, app.state.member_repo) for m in msgs]


@router.post("/{chat_id}/messages")
async def send_message(
    chat_id: str,
    body: SendMessageBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    if not body.content.strip():
        raise HTTPException(400, "Content cannot be empty")
    _verify_member_ownership(app, body.sender_id, user_id)
    msg = _messaging(app).send(
        chat_id,
        body.sender_id,
        body.content,
        mentions=body.mentioned_ids,
        signal=body.signal,
        message_type=body.message_type,
    )
    return _msg_response(msg, app.state.member_repo)


@router.post("/{chat_id}/messages/{message_id}/retract")
async def retract_message(
    chat_id: str,
    message_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    ok = _messaging(app).retract(message_id, user_id)
    if not ok:
        raise HTTPException(400, "Cannot retract: not sender, already retracted, or 2-min window expired")
    return {"status": "retracted"}


@router.delete("/{chat_id}/messages/{message_id}")
async def delete_message_for_self(
    chat_id: str,
    message_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    _messaging(app).delete_for(message_id, user_id)
    return {"status": "deleted"}


@router.post("/{chat_id}/read")
async def mark_read(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    _messaging(app).mark_read(chat_id, user_id)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Delete chat
# ---------------------------------------------------------------------------


@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    chat = app.state.chat_repo.get_by_id(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    if not _messaging(app).is_chat_member(chat_id, user_id):
        raise HTTPException(403, "Not a participant of this chat")
    app.state.chat_repo.delete(chat_id)
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# SSE stream (typing indicators fallback, messages come via Supabase Realtime)
# ---------------------------------------------------------------------------


@router.get("/{chat_id}/events")
async def stream_chat_events(
    chat_id: str,
    token: str | None = None,
    app: Annotated[Any, Depends(get_app)] = None,
):
    auth_service = getattr(app.state, "auth_service", None)
    if auth_service is not None:
        if not token:
            raise HTTPException(401, "Missing token")
        try:
            auth_service.verify_token(token)
        except ValueError as e:
            raise HTTPException(401, str(e))

    from fastapi.responses import StreamingResponse

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
# Chat mute
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Contact management (block/mute)
# ---------------------------------------------------------------------------


class SetContactBody(BaseModel):
    owner_id: str
    target_id: str
    relation: str  # "normal" | "blocked" | "muted"


@router.post("/contacts")
async def set_contact(
    body: SetContactBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    _verify_member_ownership(app, body.owner_id, user_id)
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
    _verify_member_ownership(app, owner_id, user_id)
    contact_repo = app.state.contact_repo
    contact_repo.delete(owner_id, target_id)
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Chat mute
# ---------------------------------------------------------------------------


@router.post("/{chat_id}/mute")
async def mute_chat(
    chat_id: str,
    body: MuteChatBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    _verify_member_ownership(app, body.user_id, user_id)
    mute_until_iso = datetime.fromtimestamp(body.mute_until, tz=UTC).isoformat() if body.mute_until else None
    _messaging(app).update_mute(chat_id, body.user_id, body.muted, mute_until_iso)
    return {"status": "ok", "muted": body.muted}
