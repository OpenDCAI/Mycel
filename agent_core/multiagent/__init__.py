"""Lightweight multi-agent: spawn + message-bus handoff.

A sub-agent is a *new QueryLoop sharing the parent's model client* and a filtered
tool registry — NOT a rebuilt full agent (Mycel's AgentService reconstructed an
entire LeonAgent per child). Handoff is an in-memory message bus drained by a
SteeringMiddleware before each turn.
"""

from __future__ import annotations

from agent_core.multiagent.bus import MessageBus
from agent_core.multiagent.registry import AgentEntry, AgentRegistry
from agent_core.multiagent.runtime import MultiAgentRuntime
from agent_core.multiagent.steering import SteeringMiddleware
from agent_core.multiagent.tools import multiagent_tools

__all__ = [
    "AgentEntry",
    "AgentRegistry",
    "MessageBus",
    "MultiAgentRuntime",
    "SteeringMiddleware",
    "multiagent_tools",
]
