"""Compatibility shell for the agent runtime port."""

from backend.agent_runtime.port import AgentRuntimeGatewayPort, get_agent_runtime_gateway

__all__ = ["AgentRuntimeGatewayPort", "get_agent_runtime_gateway"]
