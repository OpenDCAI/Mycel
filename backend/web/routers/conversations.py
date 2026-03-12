"""Conversations API router — list, get, send messages, SSE events."""

import asyncio
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.web.core.dependencies import get_app, get_current_member_id
from backend.web.services.agent_pool import get_or_create_agent
from backend.web.services.streaming_service import start_agent_run
from core.runtime.middleware.monitor import AgentState
from core.runtime.middleware.queue import format_conversation_message
from sandbox.thread_context import set_current_thread_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class SendMessageBody(BaseModel):
    content: str


@router.get("")
async def list_conversations(
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
) -> list[dict]:
    """List conversations for the authenticated member."""
    svc = app.state.conversation_service
    return svc.list_for_member(member_id)


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict:
    """Get conversation detail."""
    svc = app.state.conversation_service
    conv = svc.get(conversation_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    if member_id not in conv["members"]:
        raise HTTPException(403, "Not a member of this conversation")
    return conv


@router.get("/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
    limit: int = Query(50, ge=1, le=200),
    before: float | None = Query(None),
) -> list[dict]:
    """List messages in a conversation (paginated, newest last)."""
    svc = app.state.conversation_service
    if not svc.is_member(conversation_id, member_id):
        raise HTTPException(403, "Not a member of this conversation")
    return svc.list_messages(conversation_id, limit=limit, before=before)


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    body: SendMessageBody,
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict:
    """Send a message in a conversation. Routes to agent brain.

    - Agent IDLE  → start new run on brain thread
    - Agent ACTIVE → enqueue (SteeringMiddleware injects on next before_model)
    """
    if not body.content.strip():
        raise HTTPException(400, "Content cannot be empty")

    svc = app.state.conversation_service
    try:
        result = await asyncio.to_thread(svc.send_message, conversation_id, member_id, body.content)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except PermissionError as e:
        raise HTTPException(403, str(e))

    routing = result["routing"]
    brain_thread_id = routing["brain_thread_id"]
    sender_name = routing["sender_name"]
    conv_id = routing["conversation_id"]

    # Format message for brain injection
    formatted = format_conversation_message(body.content, sender_name, conv_id)

    # Get/create agent for the brain thread
    from backend.web.services.agent_pool import resolve_thread_sandbox
    sandbox_type = resolve_thread_sandbox(app, brain_thread_id)
    agent = await get_or_create_agent(app, sandbox_type, thread_id=brain_thread_id)
    set_current_thread_id(brain_thread_id)

    qm = app.state.queue_manager

    # @@@conversation-routing - same IDLE/ACTIVE pattern as threads.py:send_message
    if hasattr(agent, "runtime") and agent.runtime.current_state == AgentState.ACTIVE:
        qm.enqueue(formatted, brain_thread_id, notification_type="steer")
        return {**result["message"], "routing": "steer"}

    # Agent IDLE → start new run
    from backend.web.services.streaming_service import get_or_create_thread_buffer
    lock_key = brain_thread_id
    locks_guard = app.state.thread_locks_guard
    async with locks_guard:
        if lock_key not in app.state.thread_locks:
            app.state.thread_locks[lock_key] = asyncio.Lock()
        lock = app.state.thread_locks[lock_key]

    async with lock:
        if hasattr(agent, "runtime") and not agent.runtime.transition(AgentState.ACTIVE):
            # Race: became active between check and lock
            qm.enqueue(formatted, brain_thread_id, notification_type="steer")
            return {**result["message"], "routing": "steer"}
        run_id = start_agent_run(agent, brain_thread_id, formatted, app)

    return {**result["message"], "routing": "direct", "run_id": run_id}
