"""Agent runtime port used by web routes and chat delivery."""

from __future__ import annotations

from typing import Any, Protocol

from protocols.agent_runtime import (
    AgentChatDeliveryEnvelope,
    AgentChatDeliveryResult,
    AgentThreadInputEnvelope,
    AgentThreadInputResult,
)


class AgentRuntimeGatewayPort(Protocol):
    async def dispatch_chat(self, envelope: AgentChatDeliveryEnvelope) -> AgentChatDeliveryResult: ...

    async def dispatch_thread_input(self, envelope: AgentThreadInputEnvelope) -> AgentThreadInputResult: ...


def get_agent_runtime_gateway(app: Any) -> AgentRuntimeGatewayPort:
    return app.state.agent_runtime_gateway
