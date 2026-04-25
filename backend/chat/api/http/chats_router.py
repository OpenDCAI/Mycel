from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from backend.chat.api.http.dependencies import (
    get_chat_event_bus,
    get_chat_join_request_service,
    get_chat_repo,
    get_contact_repo,
    get_current_user_id,
    get_messaging_service,
    get_relationship_service,
    get_thread_repo,
    get_user_repo,
)
from messaging.errors import ChatNotCaughtUpError
from messaging.social_access import can_group_chat_with_participant
from messaging.user_ownership import is_owned_by_viewer

router = APIRouter(prefix="/api/chats", tags=["chats"])


class CreateChatBody(BaseModel):
    user_ids: list[str]
    title: str | None = None


class SendMessageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    mentioned_ids: list[str] | None = None
    reply_to: str | None = None
    enforce_caught_up: bool = False


class MuteChatBody(BaseModel):
    user_id: str
    muted: bool
    mute_until: float | None = None


class ChatJoinRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str | None = None


class ChatJoinRequestActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pass


def _map_chat_join_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(404, str(exc))
    if isinstance(exc, PermissionError):
        return HTTPException(403, str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(409, str(exc))
    raise exc


def _verify_user_ownership(messaging_service: Any, sender_id: str, user_id: str) -> None:
    # @@@thread-social-owner-check - sender_id can be a thread-owned social user_id, so
    # ownership must resolve through the thread back to the owning agent user before checking owner.
    sender = _resolve_display_user(messaging_service, sender_id)
    if not sender:
        raise HTTPException(403, "User not found")
    if is_owned_by_viewer(user_id, sender):
        return
    raise HTTPException(403, "User does not belong to you")


def _get_accessible_chat_or_404(chat_repo: Any, messaging_service: Any, chat_id: str, user_id: str) -> Any:
    chat = chat_repo.get_by_id(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    if not messaging_service.is_chat_member(chat_id, user_id):
        raise HTTPException(403, "Not a participant of this chat")
    return chat


def _resolve_display_user(messaging_service: Any, social_user_id: str) -> Any | None:
    return messaging_service.resolve_display_user(social_user_id)


def _validate_chat_participant_ids(
    user_repo: Any,
    thread_repo: Any,
    participant_ids: list[str],
    requester_user_id: str,
) -> list[str]:
    validated: list[str] = []
    for participant_id in participant_ids:
        if participant_id == requester_user_id:
            validated.append(participant_id)
            continue
        if thread_repo.get_by_user_id(participant_id) is not None:
            validated.append(participant_id)
            continue
        candidate = user_repo.get_by_id(participant_id)
        if candidate is not None:
            validated.append(participant_id)
            continue
        raise ValueError(f"Unknown chat participant id: {participant_id}")
    return validated


def _is_owned_participant(user_repo: Any, participant_id: str, requester_user_id: str) -> bool:
    participant = user_repo.get_by_id(participant_id)
    return is_owned_by_viewer(requester_user_id, participant)


def _validate_requester_is_participant(user_repo: Any, participant_ids: list[str], requester_user_id: str) -> None:
    for participant_id in participant_ids:
        if participant_id == requester_user_id:
            return
        if _is_owned_participant(user_repo, participant_id, requester_user_id):
            return
    raise ValueError("Chat participants must include the requester or a requester-owned participant")


def _validate_group_chat_relationships(
    relationship_service: Any,
    contact_repo: Any,
    user_repo: Any,
    participant_ids: list[str],
    requester_user_id: str,
) -> None:
    for participant_id in dict.fromkeys(participant_ids):
        if participant_id == requester_user_id or _is_owned_participant(user_repo, participant_id, requester_user_id):
            continue
        try:
            participant_user = user_repo.get_by_id(participant_id)
            if can_group_chat_with_participant(
                viewer_user_id=requester_user_id,
                participant_user_id=participant_id,
                participant_user=participant_user,
                contact_repo=contact_repo,
                relationship_service=relationship_service,
            ):
                continue
        except RuntimeError as exc:
            raise ValueError(str(exc)) from exc
        raise ValueError(f"Active relationship required for group chat participant: {participant_id}")


@router.get("")
def list_chats(
    user_id: Annotated[str, Depends(get_current_user_id)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
):
    return messaging_service.list_chats_for_user(user_id)


@router.post("")
def create_chat(
    body: CreateChatBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    user_repo: Annotated[Any, Depends(get_user_repo)],
    thread_repo: Annotated[Any, Depends(get_thread_repo)],
    contact_repo: Annotated[Any, Depends(get_contact_repo)],
    relationship_service: Annotated[Any, Depends(get_relationship_service)],
):
    try:
        participant_ids = _validate_chat_participant_ids(user_repo, thread_repo, body.user_ids, user_id)
        _validate_requester_is_participant(user_repo, participant_ids, user_id)
        if len(participant_ids) >= 3:
            _validate_group_chat_relationships(
                relationship_service,
                contact_repo,
                user_repo,
                participant_ids,
                user_id,
            )
            chat = messaging_service.create_group_chat(participant_ids, body.title)
        else:
            chat = messaging_service.find_or_create_chat(participant_ids, body.title)
        return {
            "id": chat["id"],
            "title": chat.get("title"),
            "status": chat.get("status"),
            "created_at": chat.get("created_at"),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{chat_id}")
def get_chat(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_repo: Annotated[Any, Depends(get_chat_repo)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
):
    chat = _get_accessible_chat_or_404(chat_repo, messaging_service, chat_id, user_id)
    return messaging_service.get_chat_detail(chat)


@router.get("/{chat_id}/messages")
def list_messages(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    limit: int = Query(50, ge=1, le=200),
    before: str | None = Query(None),
):
    if not messaging_service.is_chat_member(chat_id, user_id):
        raise HTTPException(403, "Not a participant of this chat")
    return messaging_service.list_message_responses(chat_id, limit=limit, before=before, viewer_id=user_id)


@router.get("/{chat_id}/join-requests")
def list_chat_join_requests(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_join_request_service: Annotated[Any, Depends(get_chat_join_request_service)],
):
    try:
        return chat_join_request_service.list_for_chat(chat_id, user_id)
    except Exception as exc:
        raise _map_chat_join_error(exc) from exc


@router.post("/{chat_id}/join-requests")
def request_chat_join(
    chat_id: str,
    body: ChatJoinRequestBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_join_request_service: Annotated[Any, Depends(get_chat_join_request_service)],
):
    try:
        return chat_join_request_service.request(chat_id, user_id, body.message)
    except Exception as exc:
        raise _map_chat_join_error(exc) from exc


@router.post("/{chat_id}/join-requests/{request_id}/approve")
def approve_chat_join(
    chat_id: str,
    request_id: str,
    body: ChatJoinRequestActionBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_join_request_service: Annotated[Any, Depends(get_chat_join_request_service)],
):
    try:
        return chat_join_request_service.approve(chat_id, request_id, user_id)
    except Exception as exc:
        raise _map_chat_join_error(exc) from exc


@router.post("/{chat_id}/join-requests/{request_id}/reject")
def reject_chat_join(
    chat_id: str,
    request_id: str,
    body: ChatJoinRequestActionBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_join_request_service: Annotated[Any, Depends(get_chat_join_request_service)],
):
    try:
        return chat_join_request_service.reject(chat_id, request_id, user_id)
    except Exception as exc:
        raise _map_chat_join_error(exc) from exc


@router.post("/{chat_id}/messages")
def send_message(
    chat_id: str,
    body: SendMessageBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
):
    if not body.content.strip():
        raise HTTPException(400, "Content cannot be empty")
    sender_id = user_id
    _verify_user_ownership(messaging_service, sender_id, user_id)
    if not messaging_service.is_chat_member(chat_id, sender_id):
        raise HTTPException(403, "Not a participant of this chat")
    try:
        msg = messaging_service.send(
            chat_id,
            sender_id,
            body.content,
            mentions=body.mentioned_ids,
            signal=None,
            message_type="human",
            reply_to=body.reply_to,
            enforce_caught_up=body.enforce_caught_up,
        )
    except ChatNotCaughtUpError as exc:
        raise HTTPException(409, str(exc)) from exc
    return messaging_service.project_message_response(msg)


@router.get("/{chat_id}/messages/unread")
def list_unread_messages(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
):
    if not messaging_service.is_chat_member(chat_id, user_id):
        raise HTTPException(403, "Not a participant of this chat")
    return [messaging_service.project_message_response(msg) for msg in messaging_service.list_unread(chat_id, user_id)]


@router.post("/{chat_id}/messages/{message_id}/retract")
def retract_message(
    chat_id: str,
    message_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
):
    ok = messaging_service.retract(message_id, user_id)
    if not ok:
        raise HTTPException(400, "Cannot retract: not sender, already retracted, or 2-min window expired")
    return {"status": "retracted"}


@router.delete("/{chat_id}/messages/{message_id}")
def delete_message_for_self(
    chat_id: str,
    message_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
):
    messaging_service.delete_for(message_id, user_id)
    return {"status": "deleted"}


@router.post("/{chat_id}/read")
def mark_read(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
):
    if not messaging_service.is_chat_member(chat_id, user_id):
        raise HTTPException(403, "Not a participant of this chat")
    messaging_service.mark_read(chat_id, user_id)
    return {"status": "ok"}


@router.delete("/{chat_id}")
def delete_chat(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_repo: Annotated[Any, Depends(get_chat_repo)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
):
    _get_accessible_chat_or_404(chat_repo, messaging_service, chat_id, user_id)
    chat_repo.delete(chat_id)
    return {"status": "deleted"}


@router.get("/{chat_id}/events")
async def stream_chat_events(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_repo: Annotated[Any, Depends(get_chat_repo)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    chat_event_bus: Annotated[Any, Depends(get_chat_event_bus)],
):
    _get_accessible_chat_or_404(chat_repo, messaging_service, chat_id, user_id)

    from fastapi.responses import StreamingResponse

    queue = chat_event_bus.subscribe(chat_id)

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
            chat_event_bus.unsubscribe(chat_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/{chat_id}/mute")
def mute_chat(
    chat_id: str,
    body: MuteChatBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
):
    _verify_user_ownership(messaging_service, body.user_id, user_id)
    mute_until_iso = datetime.fromtimestamp(body.mute_until, tz=UTC).isoformat() if body.mute_until else None
    messaging_service.update_mute(chat_id, body.user_id, body.muted, mute_until_iso)
    return {"status": "ok", "muted": body.muted}
