"""Messaging API router — replaces chats.py.

All operations go through MessagingService (Supabase-backed).
No legacy fallback.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.web.core.dependencies import get_app, get_current_user_id
from backend.web.utils.serializers import avatar_url
from storage.contracts import MemberType

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
    reply_to: str | None = None


class MuteChatBody(BaseModel):
    user_id: str
    muted: bool
    mute_until: float | None = None


class PinChatBody(BaseModel):
    pinned: bool


class PatchChatBody(BaseModel):
    title: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _messaging(app: Any):
    svc = getattr(app.state, "messaging_service", None)
    if svc is None:
        raise HTTPException(503, "MessagingService not initialized")
    return svc


def _verify_member_ownership(app: Any, member_id: str, user_id: str) -> None:
    # @@@thread-social-owner-check - sender_id can be a thread-owned social user_id, so
    # ownership must resolve through the thread back to the template member before checking owner.
    member = _resolve_display_member(app, member_id)
    if not member:
        raise HTTPException(403, "Member not found")
    if member.id == user_id:
        return  # human member sending as themselves
    if member.owner_user_id == user_id:
        return  # agent owned by current user
    raise HTTPException(403, "Member does not belong to you")


def _get_accessible_chat_or_404(app: Any, chat_id: str, user_id: str) -> Any:
    chat = app.state.chat_repo.get_by_id(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    if not _messaging(app).is_chat_member(chat_id, user_id):
        raise HTTPException(403, "Not a participant of this chat")
    return chat


def _resolve_display_member(app: Any, social_user_id: str) -> Any | None:
    member = app.state.member_repo.get_by_id(social_user_id)
    if member is not None:
        return member
    thread_repo = getattr(app.state, "thread_repo", None)
    if thread_repo is None:
        return None
    thread = thread_repo.get_by_user_id(social_user_id)
    if thread is None:
        return None
    member_id = thread.get("member_id")
    if not member_id:
        return None
    return app.state.member_repo.get_by_id(member_id)


def _validate_chat_participant_ids(app: Any, participant_ids: list[str], requester_user_id: str) -> list[str]:
    member_repo = getattr(app.state, "member_repo", None)
    thread_repo = getattr(app.state, "thread_repo", None)
    # @@@group-chat-actor-boundary - template member ids are display/config identities,
    # not deliverable chat actors. Reject them loudly at ingress instead of guessing.
    # Human members: member.id IS their social user ID — accept directly.
    # Pre-fetch all members in one batch to avoid N+1 per participant.
    known_members = (
        member_repo.get_by_ids([p for p in participant_ids if p != requester_user_id])
        if member_repo else {}
    )
    validated: list[str] = []
    for participant_id in participant_ids:
        if participant_id == requester_user_id:
            validated.append(participant_id)
            continue
        if thread_repo is not None and thread_repo.get_by_user_id(participant_id) is not None:
            validated.append(participant_id)
            continue
        member = known_members.get(participant_id)
        if member is not None:
            if member.type != MemberType.HUMAN:
                raise ValueError(f"Agent participant ids must be actor user_ids, not template member_id: {participant_id}")
        validated.append(participant_id)
    return validated


def _msg_response(m: dict[str, Any], app: Any) -> dict[str, Any]:
    sender = _resolve_display_member(app, m.get("sender_id", ""))
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
        participant_ids = _validate_chat_participant_ids(app, body.user_ids, user_id)
        if len(participant_ids) >= 3:
            chat = _messaging(app).create_group_chat(participant_ids, body.title)
        else:
            chat = _messaging(app).find_or_create_chat(participant_ids, body.title)
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
    chat = _get_accessible_chat_or_404(app, chat_id, user_id)
    members_list = _messaging(app).list_chat_members(chat_id)
    members_info = []
    read_status = {}
    for m in members_list:
        uid = m.get("user_id")
        if not uid:
            continue
        read_status[uid] = m.get("last_read_at")
        mem = _resolve_display_member(app, uid)
        if mem:
            members_info.append(
                {
                    "id": uid,
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
        "read_status": read_status,  # {user_id: last_read_at_iso}
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
    return [_msg_response(m, app) for m in msgs]


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
        reply_to=body.reply_to,
    )
    return _msg_response(msg, app)


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


@router.patch("/{chat_id}")
async def update_chat(
    chat_id: str,
    body: PatchChatBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Rename a chat (title)."""
    _get_accessible_chat_or_404(app, chat_id, user_id)
    app.state.chat_repo.update_title(chat_id, body.title)
    return {"status": "ok", "title": body.title}


@router.post("/{chat_id}/leave")
async def leave_chat(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Leave a group chat (removes membership; 1:1 chats are deleted)."""
    _get_accessible_chat_or_404(app, chat_id, user_id)
    members = _messaging(app).list_chat_members(chat_id)
    if len(members) <= 2:
        # 1:1 — delete the chat entirely
        app.state.chat_repo.delete(chat_id)
        return {"status": "deleted"}
    # Group — remove just this member
    app.state.chat_member_repo.remove_member(chat_id, user_id)
    return {"status": "left"}


@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    _get_accessible_chat_or_404(app, chat_id, user_id)
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
    if not token:
        raise HTTPException(401, "Missing token")
    try:
        app.state.auth_service.verify_token(token)
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


# ---------------------------------------------------------------------------
# Message search
# @@@route-order: must be registered before /{chat_id} dynamic routes
# ---------------------------------------------------------------------------


@router.get("/messages/search")
async def search_messages(
    q: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    results = _messaging(app).search_messages(q)
    return [_msg_response(m, app) for m in results]


# ---------------------------------------------------------------------------
# Unread count
# ---------------------------------------------------------------------------


@router.get("/{chat_id}/unread")
async def get_unread_count(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    if not _messaging(app).is_chat_member(chat_id, user_id):
        raise HTTPException(403, "Not a participant of this chat")
    count = _messaging(app).count_unread(chat_id, user_id)
    return {"count": count}


# ---------------------------------------------------------------------------
# Pin chat
# ---------------------------------------------------------------------------


@router.put("/{chat_id}/pin")
async def pin_chat(
    chat_id: str,
    body: PinChatBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    _get_accessible_chat_or_404(app, chat_id, user_id)
    app.state.chat_member_repo.update_pinned(chat_id, user_id, body.pinned)
    return {"status": "ok", "pinned": body.pinned}
