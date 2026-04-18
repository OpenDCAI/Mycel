"""Agent Runtime Gateway facade for service-to-service dispatch."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.protocols import agent_runtime as agent_runtime_protocol
from backend.web.services.agent_runtime_chat_handler import NativeAgentChatDeliveryHandler
from backend.web.services.agent_runtime_thread_handler import NativeAgentThreadInputHandler


class NativeAgentRuntimeGateway:
    """In-process Agent-side gateway for native Mycel runtime dispatch."""

    def __init__(
        self,
        app: Any,
        *,
        chat_handlers: Mapping[str, Any] | None = None,
        thread_input_handler: Any | None = None,
    ) -> None:
        self._chat_handlers = dict(chat_handlers or {"mycel": NativeAgentChatDeliveryHandler(app)})
        self._thread_input_handler = thread_input_handler or NativeAgentThreadInputHandler(app)

    async def dispatch_chat(
        self, envelope: agent_runtime_protocol.AgentChatDeliveryEnvelope
    ) -> agent_runtime_protocol.AgentGatewayDeliveryResult:
        handler = self._chat_handlers.get(envelope.recipient.runtime_source)
        if handler is None:
            raise ValueError(f"No Agent chat runtime handler registered for runtime_source={envelope.recipient.runtime_source!r}")
        return await handler.dispatch(envelope)

    async def dispatch_thread_input(self, envelope: agent_runtime_protocol.AgentThreadInputEnvelope) -> dict[str, Any]:
        """Route direct thread input through the Agent-side gateway."""
        return await self._thread_input_handler.dispatch(envelope)
