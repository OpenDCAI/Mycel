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
    # @@@agent-runtime-port-borrowed-state - web routes still read the agent
    # runtime gateway from app state, but they now borrow it through the
    # threads_runtime_state bundle instead of a loose top-level attribute.
    return app.state.threads_runtime_state.agent_runtime_gateway
