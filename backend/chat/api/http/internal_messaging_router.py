"""Internal messaging routes for cross-backend agent chat access."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.chat.api.http.dependencies import get_messaging_service

router = APIRouter(prefix="/api/internal/messaging", tags=["chat-internal"])


class DirectChatLookupBody(BaseModel):
    actor_id: str
    target_id: str


class FindOrCreateChatBody(BaseModel):
    user_ids: list[str]
    title: str | None = None


class InternalSendMessageBody(BaseModel):
    sender_id: str
    content: str
    message_type: str = "human"
    content_type: str = "text"
    mentions: list[str] | None = None
    signal: str | None = None
    reply_to: str | None = None
    ai_metadata: dict[str, Any] | None = None
    enforce_caught_up: bool = False


class MarkReadBody(BaseModel):
    user_id: str


def _display_user_payload(user: Any) -> dict[str, Any]:
    return {
        "id": getattr(user, "id", None),
        "type": getattr(user, "type", None),
        "display_name": getattr(user, "display_name", None),
        "owner_user_id": getattr(user, "owner_user_id", None),
        "avatar_url": getattr(user, "avatar_url", None),
    }


@router.get("/display-users/{social_user_id}")
def resolve_display_user(
    social_user_id: str,
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
) -> dict[str, Any]:
    user = messaging_service.resolve_display_user(social_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Display user not found")
    return _display_user_payload(user)


@router.get("/chats")
def list_chats_for_user(
    user_id: str,
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
) -> list[dict[str, Any]]:
    return messaging_service.list_chats_for_user(user_id)


@router.post("/direct-chat-id")
def find_direct_chat_id(
    body: DirectChatLookupBody,
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
) -> dict[str, Any]:
    return {"chat_id": messaging_service.find_direct_chat_id(body.actor_id, body.target_id)}


@router.post("/chats/find-or-create")
def find_or_create_chat(
    body: FindOrCreateChatBody,
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
) -> dict[str, Any]:
    try:
        return messaging_service.find_or_create_chat(body.user_ids, body.title)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/chats/{chat_id}/messages")
def list_messages(
    chat_id: str,
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    limit: int = Query(50, ge=1, le=200),
    before: str | None = Query(None),
    viewer_id: str | None = Query(None),
) -> list[dict[str, Any]]:
    return messaging_service.list_messages(chat_id, limit=limit, before=before, viewer_id=viewer_id)


@router.get("/chats/{chat_id}/messages/by-time-range")
def list_messages_by_time_range(
    chat_id: str,
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    after: str | None = Query(None),
    before: str | None = Query(None),
) -> list[dict[str, Any]]:
    return messaging_service.list_messages_by_time_range(chat_id, after=after, before=before)


@router.get("/chats/{chat_id}/messages/unread")
def list_unread_messages(
    chat_id: str,
    user_id: str,
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
) -> list[dict[str, Any]]:
    return messaging_service.list_unread(chat_id, user_id)


@router.post("/chats/{chat_id}/messages/send")
def send_message(
    chat_id: str,
    body: InternalSendMessageBody,
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
) -> dict[str, Any]:
    return messaging_service.send(
        chat_id,
        body.sender_id,
        body.content,
        message_type=body.message_type,
        content_type=body.content_type,
        mentions=body.mentions,
        signal=body.signal,
        reply_to=body.reply_to,
        ai_metadata=body.ai_metadata,
        enforce_caught_up=body.enforce_caught_up,
    )


@router.post("/chats/{chat_id}/read")
def mark_read(
    chat_id: str,
    body: MarkReadBody,
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
) -> dict[str, Any]:
    messaging_service.mark_read(chat_id, body.user_id)
    return {"status": "ok"}


@router.get("/chats/{chat_id}/members/{user_id}/is-member")
def is_chat_member(
    chat_id: str,
    user_id: str,
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
) -> dict[str, Any]:
    return {"is_member": messaging_service.is_chat_member(chat_id, user_id)}


@router.get("/chats/{chat_id}/unread-count")
def count_unread(
    chat_id: str,
    user_id: str,
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
) -> dict[str, Any]:
    return {"count": messaging_service.count_unread(chat_id, user_id)}


@router.get("/messages/search")
def search_messages(
    query: str,
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    chat_id: str | None = Query(None),
) -> list[dict[str, Any]]:
    return messaging_service.search_messages(query, chat_id=chat_id)
