"""Messaging API router — replaces chats.py.

All operations go through MessagingService (Supabase-backed).
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.web.core.dependencies import get_app, get_current_user_id
from backend.web.services.social_access_service import ACTIVE_CHAT_RELATIONSHIP_STATES, has_active_contact

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


def _verify_user_ownership(app: Any, sender_id: str, user_id: str) -> None:
    # @@@thread-social-owner-check - sender_id can be a thread-owned social user_id, so
    # ownership must resolve through the thread back to the owning agent user before checking owner.
    sender = _resolve_display_user(app, sender_id)
    if not sender:
        raise HTTPException(403, "User not found")
    if sender.id == user_id:
        return  # human user sending as themselves
    if sender.owner_user_id == user_id:
        return  # agent owned by current user
    raise HTTPException(403, "User does not belong to you")


def _get_accessible_chat_or_404(app: Any, chat_id: str, user_id: str) -> Any:
    chat = app.state.chat_repo.get_by_id(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    if not _messaging(app).is_chat_member(chat_id, user_id):
        raise HTTPException(403, "Not a participant of this chat")
    return chat


def _resolve_display_user(app: Any, social_user_id: str) -> Any | None:
    return _messaging(app).resolve_display_user(social_user_id)


def _validate_chat_participant_ids(app: Any, participant_ids: list[str], requester_user_id: str) -> list[str]:
    user_repo = getattr(app.state, "user_repo", None)
    thread_repo = getattr(app.state, "thread_repo", None)
    validated: list[str] = []
    for participant_id in participant_ids:
        if participant_id == requester_user_id:
            validated.append(participant_id)
            continue
        if thread_repo is not None and thread_repo.get_by_user_id(participant_id) is not None:
            validated.append(participant_id)
            continue
        # @@@group-chat-actor-boundary - agent user ids are display/config identities,
        # not deliverable chat actors. Reject them loudly at ingress instead of guessing.
        if user_repo is not None:
            candidate = user_repo.get_by_id(participant_id)
            if candidate is not None and getattr(candidate, "owner_user_id", None) is None:
                validated.append(participant_id)
                continue
            if candidate is not None and getattr(candidate, "owner_user_id", None) is not None:
                raise ValueError(f"Agent participant ids must be actor user_ids, not agent_user_id: {participant_id}")
        # @@@chat-participant-ingress-boundary - group chat creation must reject
        # unknown ids loudly at ingress instead of letting storage FKs decide.
        raise ValueError(f"Unknown chat participant id: {participant_id}")
    return validated


def _is_owned_participant(app: Any, participant_id: str, requester_user_id: str) -> bool:
    user_repo = getattr(app.state, "user_repo", None)
    if user_repo is None:
        return False
    participant = user_repo.get_by_id(participant_id)
    return getattr(participant, "owner_user_id", None) == requester_user_id


def _participant_access_targets(app: Any, participant_id: str) -> list[str]:
    user_repo = getattr(app.state, "user_repo", None)
    participant = user_repo.get_by_id(participant_id) if user_repo is not None else None
    owner_user_id = getattr(participant, "owner_user_id", None)
    return [participant_id, str(owner_user_id)] if owner_user_id else [participant_id]


def _validate_group_chat_relationships(app: Any, participant_ids: list[str], requester_user_id: str) -> None:
    svc = getattr(app.state, "relationship_service", None)
    if svc is None:
        raise ValueError("Relationship service is required for group chat creation")
    contact_repo = getattr(app.state, "contact_repo", None)
    for participant_id in dict.fromkeys(participant_ids):
        if participant_id == requester_user_id or _is_owned_participant(app, participant_id, requester_user_id):
            continue
        try:
            access_targets = _participant_access_targets(app, participant_id)
            if any(has_active_contact(contact_repo, requester_user_id, target_id) for target_id in access_targets):
                continue
        except RuntimeError as exc:
            raise ValueError(str(exc)) from exc
        states = [svc.get_state(requester_user_id, target_id) for target_id in access_targets]
        if not any(state in ACTIVE_CHAT_RELATIONSHIP_STATES for state in states):
            raise ValueError(f"Active relationship required for group chat participant: {participant_id}")


# ---------------------------------------------------------------------------
# Chat list / create
# ---------------------------------------------------------------------------


@router.get("")
def list_chats(
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    return _messaging(app).list_chats_for_user(user_id)


@router.post("")
def create_chat(
    body: CreateChatBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    try:
        participant_ids = _validate_chat_participant_ids(app, body.user_ids, user_id)
        if len(participant_ids) >= 3:
            _validate_group_chat_relationships(app, participant_ids, user_id)
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
def get_chat(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    chat = _get_accessible_chat_or_404(app, chat_id, user_id)
    return _messaging(app).get_chat_detail(chat)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


@router.get("/{chat_id}/messages")
def list_messages(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
    limit: int = Query(50, ge=1, le=200),
    before: str | None = Query(None),
):
    if not _messaging(app).is_chat_member(chat_id, user_id):
        raise HTTPException(403, "Not a participant of this chat")
    return _messaging(app).list_message_responses(chat_id, limit=limit, before=before, viewer_id=user_id)


@router.post("/{chat_id}/messages")
def send_message(
    chat_id: str,
    body: SendMessageBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    if not body.content.strip():
        raise HTTPException(400, "Content cannot be empty")
    _verify_user_ownership(app, body.sender_id, user_id)
    msg = _messaging(app).send(
        chat_id,
        body.sender_id,
        body.content,
        mentions=body.mentioned_ids,
        signal=body.signal,
        message_type=body.message_type,
    )
    return _messaging(app).project_message_response(msg)


@router.post("/{chat_id}/messages/{message_id}/retract")
def retract_message(
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
def delete_message_for_self(
    chat_id: str,
    message_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    _messaging(app).delete_for(message_id, user_id)
    return {"status": "deleted"}


@router.post("/{chat_id}/read")
def mark_read(
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
def delete_chat(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    _get_accessible_chat_or_404(app, chat_id, user_id)
    app.state.chat_repo.delete(chat_id)
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------


@router.get("/{chat_id}/events")
async def stream_chat_events(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)] = None,
):
    _get_accessible_chat_or_404(app, chat_id, user_id)

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
def mute_chat(
    chat_id: str,
    body: MuteChatBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    _verify_user_ownership(app, body.user_id, user_id)
    mute_until_iso = datetime.fromtimestamp(body.mute_until, tz=UTC).isoformat() if body.mute_until else None
    _messaging(app).update_mute(chat_id, body.user_id, body.muted, mute_until_iso)
    return {"status": "ok", "muted": body.muted}
