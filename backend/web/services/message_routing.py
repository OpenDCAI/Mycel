"""Unified message routing: IDLE → start run, ACTIVE → enqueue."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.runtime.middleware.monitor import AgentState
from core.runtime.middleware.queue.formatters import format_steer_reminder

logger = logging.getLogger(__name__)


async def route_message_to_brain(
    app: Any,
    thread_id: str,
    content: str,
    source: str = "owner",
    sender_name: str | None = None,
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

    if hasattr(agent, "runtime") and agent.runtime.current_state == AgentState.ACTIVE:
        qm.enqueue(format_steer_reminder(content), thread_id, "steer",
                    source=source, sender_name=sender_name)
        return {"status": "injected", "routing": "steer", "thread_id": thread_id}

    # IDLE path — acquire lock for atomic transition
    locks = app.state.thread_locks
    async with app.state.thread_locks_guard:
        lock = locks.setdefault(thread_id, asyncio.Lock())
    async with lock:
        if hasattr(agent, "runtime") and not agent.runtime.transition(AgentState.ACTIVE):
            qm.enqueue(format_steer_reminder(content), thread_id, "steer",
                        source=source, sender_name=sender_name)
            return {"status": "injected", "routing": "steer", "thread_id": thread_id}
        run_id = start_agent_run(agent, thread_id, content, app,
                                  message_metadata={"source": source, "sender_name": sender_name})
    return {"status": "started", "routing": "direct", "run_id": run_id, "thread_id": thread_id}
