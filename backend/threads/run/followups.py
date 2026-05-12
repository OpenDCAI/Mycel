from __future__ import annotations

import logging
from typing import Any

from backend.threads.chat_adapters.runtime_thread_input_action import requeue_thread_input_item
from core.runtime.middleware.monitor import AgentState
from core.runtime.queue_metadata import queue_item_message_metadata

logger = logging.getLogger(__name__)

_start_agent_run = None


async def consume_followup_queue(agent: Any, thread_id: str, app: Any) -> None:
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
            message_metadata=queue_item_message_metadata(item),
        )
    except Exception:
        logger.exception("Failed to consume followup queue for thread %s", thread_id)
        if item:
            try:
                requeue_thread_input_item(app.state.queue_manager, thread_id, item)
            except Exception:
                logger.error("Failed to re-enqueue followup for thread %s — message lost: %.200s", thread_id, item.content)
