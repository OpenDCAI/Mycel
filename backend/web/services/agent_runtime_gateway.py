"""Compatibility shell for the Agent Runtime Gateway facade."""

from backend.agent_runtime.gateway import (
    AgentChatRuntimeHandler,
    AgentThreadInputRuntimeHandler,
    NativeAgentRuntimeGateway,
)

__all__ = [
    "AgentChatRuntimeHandler",
    "AgentThreadInputRuntimeHandler",
    "NativeAgentRuntimeGateway",
]
