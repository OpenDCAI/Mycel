"""Follow-up queue consumption helpers for thread runtime runs."""

from __future__ import annotations

import logging
from typing import Any

from core.runtime.middleware.monitor import AgentState

logger = logging.getLogger(__name__)

_start_agent_run = None


async def consume_followup_queue(agent: Any, thread_id: str, app: Any) -> None:
    """Dequeue a pending followup message and start a new run."""
    item = None
    try:
        qm = app.state.queue_manager
        if not qm.peek(thread_id) or not app:
            return
        if not (hasattr(agent, "runtime") and agent.runtime.transition(AgentState.ACTIVE)):
            return
        item = qm.dequeue(thread_id)
        if item is None:
            logger.warning("followup dequeue lost race for thread %s; reverting to IDLE", thread_id)
            if hasattr(agent, "runtime"):
                agent.runtime.transition(AgentState.IDLE)
            return
        if _start_agent_run is None:
            raise RuntimeError("thread_runtime.run.followups requires _start_agent_run binding")
        _start_agent_run(
            agent,
            thread_id,
            item.content,
            app,
            message_metadata={
                "source": item.source or "system",
                "notification_type": item.notification_type,
                "sender_name": item.sender_name,
                "sender_avatar_url": item.sender_avatar_url,
                "is_steer": getattr(item, "is_steer", False),
            },
        )
    except Exception:
        logger.exception("Failed to consume followup queue for thread %s", thread_id)
        if item:
            try:
                app.state.queue_manager.enqueue(item.content, thread_id, notification_type=item.notification_type)
            except Exception:
                logger.error("Failed to re-enqueue followup for thread %s — message lost: %.200s", thread_id, item.content)
