"""Steering Middleware - injects queued messages before model calls (non-preemptive)

Tool calls are never skipped. All pending messages are drained from the unified
SQLite queue and injected as HumanMessage(metadata={"source": "system"}) before
the next LLM call.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

try:
    from core.runtime.middleware import (
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

logger = logging.getLogger(__name__)

_STEER_NON_PREEMPTIVE_SYSTEM_NOTE = (
    "Steer requests accepted during an active run are non-preemptive. "
    "If any tool call from the interrupted run already started, it was allowed to finish and its side effects may "
    "already have happened. Do not claim that prior work was interrupted, prevented, cancelled, or rolled back. "
    "Treat the steer as instructions for what to do next after that completed work, and answer honestly about any "
    "side effects that may already exist."
)


def _is_terminal_background_notification(item: Any) -> bool:
    content = getattr(item, "content", "") or ""
    notification_type = getattr(item, "notification_type", None)
    if notification_type not in {"agent", "command"}:
        return False
    return "<task-notification>" in content or "<CommandNotification>" in content


def _is_owner_steer_message(message: Any) -> bool:
    if message.__class__.__name__ != "HumanMessage":
        return False
    metadata = getattr(message, "metadata", {}) or {}
    return bool(
        metadata.get("is_steer")
        or (metadata.get("source") == "owner" and metadata.get("notification_type") == "steer")
    )


def _apply_steer_contract(request: ModelRequest) -> ModelRequest:
    if not any(_is_owner_steer_message(message) for message in request.messages):
        return request

    system_message = request.system_message
    if system_message is None:
        return request.override(system_message=SystemMessage(content=_STEER_NON_PREEMPTIVE_SYSTEM_NOTE))

    content = getattr(system_message, "content", None)
    if isinstance(content, str):
        if _STEER_NON_PREEMPTIVE_SYSTEM_NOTE in content:
            return request
        # @@@steer-honesty-contract - mid-run steer stays a real user message in
        # durable history, but the live model call also needs an explicit
        # non-preemptive contract so it cannot overclaim that already-started
        # tool work was stopped or never produced side effects.
        return request.override(
            system_message=SystemMessage(content=f"{content}\n\n{_STEER_NON_PREEMPTIVE_SYSTEM_NOTE}")
        )

    return request.override(messages=[SystemMessage(content=_STEER_NON_PREEMPTIVE_SYSTEM_NOTE), *request.messages])


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

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        return handler(_apply_steer_contract(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        return await handler(_apply_steer_contract(request))

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
        inject_now = []
        deferred = []
        for item in items:
            if _is_terminal_background_notification(item):
                deferred.append(item)
            else:
                inject_now.append(item)
        # @@@followup-defer - terminal background notifications must never be
        # injected inline into an active run. Their stable contract is a
        # dedicated followthrough notice-only turn, regardless of the current
        # run source.
        for item in deferred:
            self._queue_manager.enqueue(
                item.content,
                thread_id,
                notification_type=item.notification_type,
                source=item.source,
                sender_entity_id=item.sender_entity_id,
                sender_name=item.sender_name,
            )
        items = inject_now
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
            messages.append(
                HumanMessage(
                    content=item.content,
                    metadata={
                        "source": source,
                        "notification_type": item.notification_type,
                        "sender_name": item.sender_name,
                        "sender_avatar_url": item.sender_avatar_url,
                        "sender_entity_id": item.sender_entity_id,
                        "is_steer": is_steer,
                    },
                )
            )

        # @@@steer-phase-boundary — emit run_done + run_start so frontend
        # breaks the turn at the steer injection point.
        # user_message is NOT emitted here — wake_handler already did it
        # at enqueue time (@@@steer-instant-feedback).
        agent_runtime = self._agent_runtime
        if has_steer and agent_runtime and hasattr(agent_runtime, "emit_activity_event"):
            agent_runtime.emit_activity_event(
                {
                    "event": "run_done",
                    "data": json.dumps({"thread_id": thread_id}),
                }
            )
            agent_runtime.emit_activity_event(
                {
                    "event": "run_start",
                    "data": json.dumps({"thread_id": thread_id, "showing": True}),
                }
            )

        return {"messages": messages}

    async def abefore_model(
        self,
        state: Any,
        runtime: Any,
        config: RunnableConfig | None = None,
    ) -> dict[str, Any] | None:
        """Async version of before_model."""
        return self.before_model(state, runtime, config)
