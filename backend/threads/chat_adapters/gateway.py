from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from protocols import agent_runtime as agent_runtime_protocol

from .runtime_metadata import thread_input_from_notification


class AgentThreadInputRuntimeHandler(Protocol):
    async def dispatch(
        self, envelope: agent_runtime_protocol.AgentThreadInputEnvelope
    ) -> agent_runtime_protocol.AgentThreadInputResult: ...


class AgentRuntimeNotificationHandler(Protocol):
    async def dispatch_notification(
        self, envelope: agent_runtime_protocol.AgentRuntimeNotificationEnvelope
    ) -> agent_runtime_protocol.AgentRuntimeNotificationResult: ...


class NativeAgentRuntimeGateway:
    def __init__(
        self,
        *,
        notification_handlers: Mapping[str, AgentRuntimeNotificationHandler] | None = None,
        thread_input_handler: AgentThreadInputRuntimeHandler | None = None,
    ) -> None:
        self._notification_handlers = dict(notification_handlers or {})
        self._thread_input_handler = thread_input_handler

    async def dispatch_notification(
        self, envelope: agent_runtime_protocol.AgentRuntimeNotificationEnvelope
    ) -> agent_runtime_protocol.AgentRuntimeNotificationResult:
        if envelope.recipient.runtime_source == "mycel":
            result = await self.dispatch_thread_input(thread_input_from_notification(envelope))
            return agent_runtime_protocol.AgentRuntimeNotificationResult(status="accepted", thread_id=result.thread_id)
        handler = self._notification_handlers.get(envelope.recipient.runtime_source)
        if handler is None:
            raise ValueError(f"No Agent runtime notification handler registered for runtime_source={envelope.recipient.runtime_source!r}")
        return await handler.dispatch_notification(envelope)

    async def dispatch_thread_input(
        self, envelope: agent_runtime_protocol.AgentThreadInputEnvelope
    ) -> agent_runtime_protocol.AgentThreadInputResult:
        if self._thread_input_handler is None:
            raise ValueError("No Agent thread input runtime handler configured")
        return await self._thread_input_handler.dispatch(envelope)
