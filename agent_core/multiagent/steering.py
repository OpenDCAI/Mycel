"""SteeringMiddleware — drains an agent's bus queue before each model call.

Queued messages from other agents (or the user) are injected as HumanMessages so
the agent sees them on its next turn. This is the handoff delivery mechanism.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

from agent_core.middleware import AgentMiddleware
from agent_core.multiagent.bus import MessageBus


class SteeringMiddleware(AgentMiddleware):
    def __init__(self, *, agent_name: str, bus: MessageBus) -> None:
        self.agent_name = agent_name
        self.bus = bus

    def before_model(self, *, state: Any, runtime: Any = None, config: Any = None) -> dict | None:
        messages = self.bus.drain(self.agent_name)
        if not messages:
            return None
        injected = [HumanMessage(content=f"[message from {m.sender}] {m.content}") for m in messages]
        return {"messages": injected}
