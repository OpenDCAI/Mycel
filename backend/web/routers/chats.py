"""Chat API router — entity-to-entity communication."""

import asyncio
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.web.core.dependencies import get_app, get_current_member_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chats", tags=["chats"])


class CreateChatBody(BaseModel):
    entity_ids: list[str]
    title: str | None = None


class SendMessageBody(BaseModel):
    content: str
    sender_entity_id: str


@router.get("")
async def list_chats(
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """List all chats for the current user's entities."""
    entity_repo = app.state.entity_repo
    chat_service = app.state.chat_service

    entities = entity_repo.get_by_member_id(member_id)
    all_chats = []
    seen_ids: set[str] = set()
    for e in entities:
        chats = chat_service.list_chats_for_entity(e.id)
        for c in chats:
            if c["id"] not in seen_ids:
                seen_ids.add(c["id"])
                all_chats.append(c)
    return all_chats


@router.post("")
async def create_chat(
    body: CreateChatBody,
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Create a chat between entities."""
    chat_service = app.state.chat_service
    try:
        chat = chat_service.find_or_create_chat(body.entity_ids, body.title)
        return {"id": chat.id, "title": chat.title, "status": chat.status, "created_at": chat.created_at}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{chat_id}")
async def get_chat(
    chat_id: str,
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Get chat details."""
    chat = app.state.chat_repo.get_by_id(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    return {"id": chat.id, "title": chat.title, "status": chat.status, "created_at": chat.created_at}


@router.get("/{chat_id}/messages")
async def list_messages(
    chat_id: str,
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
    limit: int = Query(50, ge=1, le=200),
    before: float | None = Query(None),
):
    """List messages in a chat."""
    msgs = app.state.chat_message_repo.list_by_chat(chat_id, limit=limit, before=before)
    return [
        {"id": m.id, "chat_id": m.chat_id, "sender_entity_id": m.sender_entity_id, "content": m.content, "created_at": m.created_at}
        for m in msgs
    ]


@router.post("/{chat_id}/messages")
async def send_message(
    chat_id: str,
    body: SendMessageBody,
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Send a message in a chat."""
    if not body.content.strip():
        raise HTTPException(400, "Content cannot be empty")
    chat_service = app.state.chat_service
    msg = chat_service.send_message(chat_id, body.sender_entity_id, body.content)
    return {"id": msg.id, "chat_id": msg.chat_id, "sender_entity_id": msg.sender_entity_id, "content": msg.content, "created_at": msg.created_at}


@router.get("/{chat_id}/events")
async def stream_chat_events(
    chat_id: str,
    token: str | None = None,
    app: Annotated[Any, Depends(get_app)] = None,
):
    """SSE stream for chat events. Uses ?token= for auth."""
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
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            event_bus.unsubscribe(chat_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Delete a chat."""
    chat = app.state.chat_repo.get_by_id(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    app.state.chat_repo.delete(chat_id)
    return {"status": "deleted"}
