import json
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from core.runtime.middleware import (
    AgentMiddleware,
    ModelCallResult,
    ModelRequest,
    ModelResponse,
)
from core.runtime.notifications import is_terminal_background_notification

from .manager import MessageQueueManager

_STEER_NON_PREEMPTIVE_SYSTEM_NOTE = (
    "Steer requests accepted during an active run are non-preemptive. "
    "If any tool call from the interrupted run already started, it was allowed to finish and its side effects may "
    "already have happened. Do not claim that prior work was interrupted, prevented, cancelled, or rolled back. "
    "Treat the steer as instructions for what to do next after that completed work, and answer honestly about any "
    "side effects that may already exist."
)


def _is_terminal_background_notification(item: Any) -> bool:
    return is_terminal_background_notification(
        getattr(item, "content", None),
        source="system",
        notification_type=getattr(item, "notification_type", None),
    )


def _is_owner_steer_message(message: Any) -> bool:
    if message.__class__.__name__ != "HumanMessage":
        return False
    metadata = getattr(message, "metadata", {}) or {}
    return bool(metadata.get("is_steer") or (metadata.get("source") == "owner" and metadata.get("notification_type") == "steer"))


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
        return request.override(system_message=SystemMessage(content=f"{content}\n\n{_STEER_NON_PREEMPTIVE_SYSTEM_NOTE}"))

    return request.override(messages=[SystemMessage(content=_STEER_NON_PREEMPTIVE_SYSTEM_NOTE), *request.messages])


class SteeringMiddleware(AgentMiddleware):
    def __init__(self, queue_manager: MessageQueueManager, agent_runtime: Any = None) -> None:
        self._queue_manager = queue_manager
        self._agent_runtime = agent_runtime  # our AgentRuntime, not LangGraph's Runtime

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
        thread_id = (config or {}).get("configurable", {}).get("thread_id")
        if not thread_id:
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
                sender_id=item.sender_id,
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
                        "sender_id": item.sender_id,
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
        return self.before_model(state, runtime, config)
