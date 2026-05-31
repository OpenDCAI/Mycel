"""MultiAgentRuntime — spawns child agents and routes handoff messages.

Shares one model client across all agents (cheap). Each child is a fresh
``Agent`` over a filtered tool registry + a per-child ``SteeringMiddleware``
bound to the shared bus.
"""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage

from agent_core.agent import Agent
from agent_core.loop import DEFAULT_MAX_TURNS
from agent_core.multiagent.bus import BusMessage, MessageBus
from agent_core.multiagent.registry import AgentEntry, AgentRegistry
from agent_core.multiagent.steering import SteeringMiddleware
from agent_core.ports.checkpoint import CheckpointStore
from agent_core.registry import ToolEntry, ToolRegistry

ToolFactory = Callable[[str], list[ToolEntry]]


def _last_ai_text(result: dict | None) -> str:
    if not isinstance(result, dict):
        return ""
    for message in reversed(result.get("messages", [])):
        if isinstance(message, AIMessage):
            content = message.content
            if isinstance(content, str) and content.strip():
                return content
    return ""


class MultiAgentRuntime:
    def __init__(
        self,
        *,
        model: Any,
        system_prompt: SystemMessage | str | None = None,
        tool_factory: ToolFactory | None = None,
        max_turns: int = DEFAULT_MAX_TURNS,
        checkpoint_store: CheckpointStore | None = None,
    ) -> None:
        self.model = model
        self.system_prompt = system_prompt
        self.tool_factory = tool_factory
        self.max_turns = max_turns
        self.checkpoint_store = checkpoint_store
        self.bus = MessageBus()
        self.registry = AgentRegistry()
        self._counter = itertools.count(1)
        self._tasks: dict[str, asyncio.Task] = {}

    def _next_task_id(self) -> str:
        return f"task_{next(self._counter)}"

    def build_agent(self, *, name: str, subagent_type: str = "general") -> Agent:
        """Build a child agent: shared model + filtered tools + handoff tools + steering."""
        # local import avoids a cycle (tools import the runtime type for hints)
        from agent_core.multiagent.tools import multiagent_tools

        reg = ToolRegistry()
        if self.tool_factory is not None:
            for tool in self.tool_factory(subagent_type):
                reg.register(tool)
        for tool in multiagent_tools(self, agent_name=name):
            reg.register(tool)
        steering = SteeringMiddleware(agent_name=name, bus=self.bus)
        return Agent(
            model=self.model,
            registry=reg,
            system_prompt=self.system_prompt,
            middleware=[steering],
            max_turns=self.max_turns,
            checkpoint_store=self.checkpoint_store,
        )

    async def spawn(
        self,
        *,
        name: str,
        prompt: str,
        subagent_type: str = "general",
        background: bool = False,
    ) -> dict[str, Any]:
        task_id = self._next_task_id()
        entry = AgentEntry(name=name, task_id=task_id, status="running")
        self.registry.register(entry)
        child = self.build_agent(name=name, subagent_type=subagent_type)

        async def _run() -> dict:
            try:
                result = await child.ainvoke(prompt, thread_id=name)
                entry.status = "done"
                entry.result = result
                return result
            except Exception as exc:  # noqa: BLE001 - record failure on the entry
                entry.status = "error"
                entry.result = {"error": str(exc)}
                raise

        if background:
            self._tasks[task_id] = asyncio.create_task(_run())
            return {"task_id": task_id, "name": name, "status": "running"}

        result = await _run()
        return {"task_id": task_id, "name": name, "status": entry.status, "text": _last_ai_text(result)}

    def send_message(self, *, to: str, content: str, sender: str = "user") -> dict[str, Any]:
        self.bus.enqueue(to, BusMessage(sender=sender, content=content))
        return {"delivered_to": to, "pending": self.bus.pending(to)}

    async def task_output(self, *, task_id: str, block: bool = True) -> dict[str, Any]:
        task = self._tasks.get(task_id)
        entry = self.registry.by_id(task_id)
        if entry is None:
            return {"error": f"unknown task {task_id}"}
        if task is None:  # was a synchronous spawn; already finished
            return {"task_id": task_id, "status": entry.status, "text": _last_ai_text(entry.result)}
        if not block and not task.done():
            return {"task_id": task_id, "status": "running"}
        await task
        return {"task_id": task_id, "status": entry.status, "text": _last_ai_text(entry.result)}
