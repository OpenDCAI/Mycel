from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from protocols import agent_runtime as agent_runtime_protocol


class AgentChatRuntimeHandler(Protocol):
    async def dispatch(
        self, envelope: agent_runtime_protocol.AgentChatDeliveryEnvelope
    ) -> agent_runtime_protocol.AgentChatDeliveryResult: ...


class AgentThreadInputRuntimeHandler(Protocol):
    async def dispatch(
        self, envelope: agent_runtime_protocol.AgentThreadInputEnvelope
    ) -> agent_runtime_protocol.AgentThreadInputResult: ...


class NativeAgentRuntimeGateway:
    def __init__(
        self,
        *,
        chat_handlers: Mapping[str, AgentChatRuntimeHandler] | None = None,
        thread_input_handler: AgentThreadInputRuntimeHandler | None = None,
    ) -> None:
        self._chat_handlers = dict(chat_handlers or {})
        self._thread_input_handler = thread_input_handler

    async def dispatch_chat(
        self, envelope: agent_runtime_protocol.AgentChatDeliveryEnvelope
    ) -> agent_runtime_protocol.AgentChatDeliveryResult:
        handler = self._chat_handlers.get(envelope.recipient.runtime_source)
        if handler is None:
            raise ValueError(f"No Agent chat runtime handler registered for runtime_source={envelope.recipient.runtime_source!r}")
        return await handler.dispatch(envelope)

    async def dispatch_thread_input(
        self, envelope: agent_runtime_protocol.AgentThreadInputEnvelope
    ) -> agent_runtime_protocol.AgentThreadInputResult:
        if self._thread_input_handler is None:
            raise ValueError("No Agent thread input runtime handler configured")
        return await self._thread_input_handler.dispatch(envelope)
