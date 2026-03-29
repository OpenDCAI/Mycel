"""Steering Middleware - injects queued messages before model calls (non-preemptive)

Tool calls are never skipped. All pending messages are drained from the unified
SQLite queue and injected as HumanMessage(metadata={"source": "system"}) before
the next LLM call.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

try:
    from langchain.agents.middleware.types import (
        AgentMiddleware,
        ModelCallResult,
        ModelRequest,
        ModelResponse,
        ToolCallRequest,
    )
except ImportError:

    class AgentMiddleware:
        pass

    ModelRequest = Any
    ModelResponse = Any
    ModelCallResult = Any
    ToolCallRequest = Any

from .manager import MessageQueueManager


class SteeringMiddleware(AgentMiddleware):
    """Non-preemptive steering: let all tool calls finish, inject before next LLM call.

    Flow:
    1. Tool calls execute normally (no skipping)
    2. Before next model call, drain ALL pending messages from SQLite queue
    3. Inject as HumanMessage with metadata source="system"
    4. Update runtime.visibility_context so streaming tags events correctly
    """

    def __init__(self, queue_manager: MessageQueueManager, agent_runtime: Any = None) -> None:
        self._queue_manager = queue_manager
        self._agent_runtime = agent_runtime  # our AgentRuntime, not LangGraph's Runtime

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage],
    ) -> ToolMessage:
        """Pure passthrough — never skip tool calls."""
        return handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage]],
    ) -> ToolMessage:
        """Async pure passthrough — never skip tool calls."""
        return await handler(request)

    def before_model(
        self,
        state: Any,
        runtime: Any,
        config: RunnableConfig | None = None,
    ) -> dict[str, Any] | None:
        """Drain all pending messages from unified queue and inject before model call."""
        thread_id = (config or {}).get("configurable", {}).get("thread_id")
        if not thread_id:
            logger.debug("SteeringMiddleware: no thread_id in config, skipping steer injection")
            return None

        items = self._queue_manager.drain_all(thread_id)
        rt = self._agent_runtime
        if not items:
            return None

        messages = []
        has_steer = False
        for item in items:
            source = item.source or "system"
            # is_steer may not survive DB round-trip; owner source = steer
            is_steer = item.is_steer or source == "owner"
            if is_steer:
                has_steer = True
            extra_metadata = item.extra_metadata or {}
            scheduled_task_run_id = extra_metadata.get("scheduled_task_run_id")
            if scheduled_task_run_id and rt is not None:
                from backend.scheduled_tasks.runtime import mark_run_dispatched

                if not hasattr(rt, "current_scheduled_task_run_ids"):
                    rt.current_scheduled_task_run_ids = set()
                rt.current_scheduled_task_run_ids.add(str(scheduled_task_run_id))
                run_id = str((config or {}).get("configurable", {}).get("run_id") or "")
                mark_run_dispatched(
                    str(scheduled_task_run_id),
                    thread_run_id=run_id,
                    routing="inline",
                )
            messages.append(HumanMessage(
                content=item.content,
                metadata={
                    "source": source,
                    "notification_type": item.notification_type,
                    "sender_name": item.sender_name,
                    "sender_avatar_url": item.sender_avatar_url,
                    "sender_entity_id": item.sender_entity_id,
                    "is_steer": is_steer,
                    **extra_metadata,
                },
            ))

        # @@@steer-phase-boundary — emit run_done + run_start so frontend
        # breaks the turn at the steer injection point.
        # user_message is NOT emitted here — wake_handler already did it
        # at enqueue time (@@@steer-instant-feedback).
        if has_steer and rt and hasattr(rt, "emit_activity_event"):
            rt.emit_activity_event({
                "event": "run_done",
                "data": json.dumps({"thread_id": thread_id}),
            })
            rt.emit_activity_event({
                "event": "run_start",
                "data": json.dumps({"thread_id": thread_id, "showing": True}),
            })

        return {"messages": messages}

    async def abefore_model(
        self,
        state: Any,
        runtime: Any,
        config: RunnableConfig | None = None,
    ) -> dict[str, Any] | None:
        """Async version of before_model."""
        return self.before_model(state, runtime, config)
