"""Agent — the thin assembly facade.

Replaces Mycel's 1700-line ``LeonAgent``. Given a model + tools, it wires a
``QueryLoop`` with the standard middleware stack (ToolRunner innermost) and an
``AppState``. Everything optional (checkpoint store, extra middleware, permission
checker) is injected; nothing is constructed from global config or env here.

    from agent_core import Agent
    from agent_core.builtins import default_toolset

    agent = Agent(model=my_model, tools=default_toolset("/work"), system_prompt="...")
    result = await agent.ainvoke("do the thing")
    print(result["messages"][-1].content)
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from langchain_core.messages import SystemMessage

from agent_core.abort import AbortController
from agent_core.loop import DEFAULT_MAX_TURNS, QueryLoop
from agent_core.middleware import AgentMiddleware
from agent_core.ports.checkpoint import CheckpointStore
from agent_core.registry import ToolEntry, ToolRegistry
from agent_core.runner import ToolRunner
from agent_core.state import AppState, BootstrapConfig


class Agent:
    def __init__(
        self,
        *,
        model: Any,
        tools: list[ToolEntry] | None = None,
        registry: ToolRegistry | None = None,
        system_prompt: SystemMessage | str | None = None,
        middleware: list[AgentMiddleware] | None = None,
        checkpoint_store: CheckpointStore | None = None,
        max_turns: int = DEFAULT_MAX_TURNS,
        workspace_root: str | Path | None = None,
        model_name: str | None = None,
        can_use_tool: Callable[..., Any] | None = None,
        app_state: AppState | None = None,
        abort_controller: AbortController | None = None,
    ) -> None:
        if registry is None:
            registry = ToolRegistry()
            for tool in tools or []:
                registry.register(tool)
        elif tools:
            for tool in tools:
                registry.register(tool)
        self.registry = registry

        # ToolRunner is the innermost (last) middleware: it validates, checks
        # permissions and dispatches registered tools. Caller middleware wrap it.
        stack = list(middleware or [])
        if not any(isinstance(m, ToolRunner) for m in stack):
            stack.append(ToolRunner(registry))
        self.middleware = stack

        self.app_state = app_state or AppState()
        self.bootstrap = BootstrapConfig(
            workspace_root=Path(workspace_root) if workspace_root else Path.cwd(),
            model_name=model_name or getattr(model, "model_name", None) or "agent",
        )
        self.loop = QueryLoop(
            model=model,
            registry=registry,
            system_prompt=system_prompt,
            middleware=stack,
            checkpoint_store=checkpoint_store,
            app_state=self.app_state,
            bootstrap=self.bootstrap,
            max_turns=max_turns,
            can_use_tool=can_use_tool,
            abort_controller=abort_controller,
        )

    @staticmethod
    def _config(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    @property
    def abort_controller(self) -> AbortController:
        return self.loop.abort_controller

    def abort(self) -> None:
        self.loop.abort()

    async def ainvoke(self, input: Any, *, thread_id: str = "default") -> dict:
        return await self.loop.ainvoke(input, self._config(thread_id))

    def astream(self, input: Any, *, thread_id: str = "default") -> AsyncIterator[dict]:
        return self.loop.astream(input, self._config(thread_id))

    def query(self, input: Any, *, thread_id: str = "default") -> AsyncIterator[dict]:
        return self.loop.query(input, self._config(thread_id))
