"""Unified message routing: IDLE → start run, ACTIVE → enqueue."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.runtime.middleware.monitor import AgentState
from core.runtime.middleware.queue.formatters import format_owner_message, format_owner_steer

logger = logging.getLogger(__name__)


async def route_message_to_brain(
    app: Any,
    thread_id: str,
    content: str,
    source: str = "owner",
    sender_name: str | None = None,
    sender_avatar_url: str | None = None,
) -> dict:
    """Route message to agent brain thread.

    IDLE  → start new run
    ACTIVE → enqueue as steer
    """
    from backend.web.services.agent_pool import get_or_create_agent, resolve_thread_sandbox
    from backend.web.services.streaming_service import start_agent_run

    sandbox_type = resolve_thread_sandbox(app, thread_id)
    agent = await get_or_create_agent(app, sandbox_type, thread_id=thread_id)
    qm = app.state.queue_manager

    state = agent.runtime.current_state if hasattr(agent, "runtime") else "no-runtime"
    logger.debug("[route] thread=%s state=%s source=%s", thread_id[:15], state, source)

    # @@@context-shift — only inject visibility hint when shifting from private → owner.
    # External messages arrive pre-formatted by format_chat_message (always has hint).
    needs_shift_hint = source == "owner" and agent.runtime.display_latent != "owner"

    if source == "owner" and needs_shift_hint:
        steer_content = format_owner_steer(content)
        run_content = format_owner_message(content)
    elif source == "owner":
        steer_content = content  # already in owner context, no hint needed
        run_content = content
    else:
        steer_content = content  # already wrapped by format_chat_message
        run_content = content

    if hasattr(agent, "runtime") and agent.runtime.current_state == AgentState.ACTIVE:
        qm.enqueue(steer_content, thread_id, "steer",
                    source=source, sender_name=sender_name,
                    sender_avatar_url=sender_avatar_url, is_steer=True)
        logger.debug("[route] → ENQUEUED (agent active)")
        return {"status": "injected", "routing": "steer", "thread_id": thread_id}

    # IDLE path — acquire lock for atomic transition
    locks = app.state.thread_locks
    async with app.state.thread_locks_guard:
        lock = locks.setdefault(thread_id, asyncio.Lock())
    async with lock:
        if hasattr(agent, "runtime") and not agent.runtime.transition(AgentState.ACTIVE):
            qm.enqueue(steer_content, thread_id, "steer",
                        source=source, sender_name=sender_name,
                        sender_avatar_url=sender_avatar_url, is_steer=True)
            logger.debug("[route] → ENQUEUED (transition failed)")
            return {"status": "injected", "routing": "steer", "thread_id": thread_id}
        logger.debug("[route] → START RUN (idle→active)")
        run_id = start_agent_run(agent, thread_id, run_content, app,
                                  message_metadata={"source": source, "sender_name": sender_name,
                                                     "sender_avatar_url": sender_avatar_url})
    return {"status": "started", "routing": "direct", "run_id": run_id, "thread_id": thread_id}
