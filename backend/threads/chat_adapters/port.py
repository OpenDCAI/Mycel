"""Agent runtime port used by web routes and chat delivery."""

from __future__ import annotations

from typing import Any

from protocols.agent_runtime import AgentRuntimeGateway, ThreadInputTransport


def get_thread_input_transport(app: Any) -> ThreadInputTransport:
    return app.state.threads_runtime_state.thread_input_transport


def get_agent_runtime_gateway(app: Any) -> AgentRuntimeGateway:
    runtime_state = getattr(app.state, "threads_runtime_state", None)
    gateway = getattr(runtime_state, "agent_runtime_gateway", None)
    if gateway is None:
        gateway = getattr(app.state, "agent_runtime_gateway", None)
    if gateway is None:
        raise RuntimeError("Agent runtime gateway is not configured")
    return gateway
