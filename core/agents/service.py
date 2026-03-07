"""AgentService - Registers Agent/TaskOutput/TaskStop tools into ToolRegistry.

Creates independent LeonAgent instances per spawn, uses asyncio.shield() +
wait_for() for implicit background switching. Backed by AgentRegistry (SQLite).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from core.agents.registry import AgentEntry, AgentRegistry
from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry

logger = logging.getLogger(__name__)

AGENT_SCHEMA = {
    "name": "Agent",
    "description": (
        "Launch a new agent to handle complex tasks autonomously. "
        "Use subagent_type to select a specialized agent, or omit for default. "
        "Agents run independently with their own tool stack."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "subagent_type": {
                "type": "string",
                "description": "Type of agent to spawn (e.g. 'Explore', 'Coder'). Omit for general-purpose.",
            },
            "prompt": {
                "type": "string",
                "description": "Task for the agent",
            },
            "name": {
                "type": "string",
                "description": "Name for the agent (used for SendMessage routing)",
            },
            "description": {
                "type": "string",
                "description": "Short description of what agent will do",
            },
            "run_in_background": {
                "type": "boolean",
                "default": False,
                "description": "Return immediately with task_id instead of waiting",
            },
            "resume": {
                "type": "string",
                "description": "Task ID of a previously backgrounded agent to resume",
            },
            "max_turns": {
                "type": "integer",
                "description": "Maximum turns the agent can take",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in milliseconds before auto-backgrounding (default: 300000)",
                "default": 300000,
            },
        },
        "required": ["prompt"],
    },
}

TASK_OUTPUT_SCHEMA = {
    "name": "TaskOutput",
    "description": "Get the output of a background agent task by its task_id.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The task ID returned when starting a background agent",
            },
        },
        "required": ["task_id"],
    },
}

TASK_STOP_SCHEMA = {
    "name": "TaskStop",
    "description": "Stop a running background agent task.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The task ID to stop",
            },
        },
        "required": ["task_id"],
    },
}


class _RunningTask:
    """Tracks a background asyncio.Task with its metadata."""

    def __init__(self, task: asyncio.Task, agent_id: str, thread_id: str):
        self.task = task
        self.agent_id = agent_id
        self.thread_id = thread_id

    @property
    def is_done(self) -> bool:
        return self.task.done()

    def get_result(self) -> str | None:
        if not self.task.done():
            return None
        exc = self.task.exception()
        if exc:
            return f"<tool_use_error>{exc}</tool_use_error>"
        return self.task.result()


class AgentService:
    """Registers Agent, TaskOutput, TaskStop tools into ToolRegistry.

    Creates independent LeonAgent instances for each spawn. Uses asyncio.shield()
    + wait_for() so long-running agents auto-switch to background without losing work.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        agent_registry: AgentRegistry,
        workspace_root: Path,
        model_name: str,
        queue_manager: Any | None = None,
    ):
        self._agent_registry = agent_registry
        self._workspace_root = workspace_root
        self._model_name = model_name
        self._queue_manager = queue_manager
        self._tasks: dict[str, _RunningTask] = {}  # task_id -> _RunningTask

        tool_registry.register(ToolEntry(
            name="Agent",
            mode=ToolMode.INLINE,
            schema=AGENT_SCHEMA,
            handler=self._handle_agent,
            source="AgentService",
        ))
        tool_registry.register(ToolEntry(
            name="TaskOutput",
            mode=ToolMode.INLINE,
            schema=TASK_OUTPUT_SCHEMA,
            handler=self._handle_task_output,
            source="AgentService",
        ))
        tool_registry.register(ToolEntry(
            name="TaskStop",
            mode=ToolMode.INLINE,
            schema=TASK_STOP_SCHEMA,
            handler=self._handle_task_stop,
            source="AgentService",
        ))

    async def _handle_agent(
        self,
        prompt: str,
        subagent_type: str = "General",
        name: str | None = None,
        description: str | None = None,
        run_in_background: bool = False,
        resume: str | None = None,
        max_turns: int | None = None,
        timeout: int = 300000,
    ) -> str:
        """Spawn an independent LeonAgent and run it with the given prompt."""
        from sandbox.thread_context import get_current_thread_id

        task_id = uuid.uuid4().hex[:8]
        agent_name = name or f"agent-{task_id}"

        # Reuse thread_id when resuming a previous backgrounded task
        if resume and resume in self._tasks:
            thread_id = self._tasks[resume].thread_id
        else:
            thread_id = f"subagent-{task_id}"

        parent_thread_id = get_current_thread_id()

        # Register in AgentRegistry immediately
        entry = AgentEntry(
            agent_id=task_id,
            name=agent_name,
            thread_id=thread_id,
            status="running",
            parent_agent_id=parent_thread_id,
            subagent_type=subagent_type,
        )
        await self._agent_registry.register(entry)

        # Create async task (independent LeonAgent runs inside)
        task = asyncio.create_task(
            self._run_agent(task_id, agent_name, thread_id, prompt, subagent_type, max_turns)
        )
        running = _RunningTask(task=task, agent_id=task_id, thread_id=thread_id)
        self._tasks[task_id] = running

        if run_in_background:
            return json.dumps({
                "task_id": task_id,
                "agent_name": agent_name,
                "thread_id": thread_id,
                "status": "running",
                "message": "Agent started in background. Use TaskOutput to get result.",
            }, ensure_ascii=False)

        # Wait with timeout; asyncio.shield keeps agent running if we time out
        timeout_s = timeout / 1000
        try:
            result = await asyncio.wait_for(asyncio.shield(task), timeout=timeout_s)
            await self._agent_registry.update_status(task_id, "completed")
            return result
        except asyncio.TimeoutError:
            # Auto-switch to background — agent keeps running via shield
            return json.dumps({
                "task_id": task_id,
                "agent_name": agent_name,
                "thread_id": thread_id,
                "status": "backgrounded",
                "message": (
                    f"Agent still running after {timeout}ms. "
                    "Use TaskOutput to poll for result."
                ),
            }, ensure_ascii=False)
        except Exception as e:
            await self._agent_registry.update_status(task_id, "error")
            return f"<tool_use_error>Agent failed: {e}</tool_use_error>"

    async def _run_agent(
        self,
        task_id: str,
        agent_name: str,
        thread_id: str,
        prompt: str,
        subagent_type: str,
        max_turns: int | None,
    ) -> str:
        """Create and run an independent LeonAgent, collect its text output."""
        # Lazy import avoids circular dependency (agent.py imports AgentService)
        from agent import create_leon_agent
        from sandbox.thread_context import set_current_thread_id

        agent = None
        try:
            agent = create_leon_agent(
                model_name=self._model_name,
                workspace_root=self._workspace_root,
                verbose=False,
            )

            set_current_thread_id(thread_id)
            config = {"configurable": {"thread_id": thread_id}}
            output_parts: list[str] = []

            async for chunk in agent.agent.astream(
                {"messages": [{"role": "user", "content": prompt}]},
                config=config,
                stream_mode="updates",
            ):
                for _, node_update in chunk.items():
                    if not isinstance(node_update, dict):
                        continue
                    msgs = node_update.get("messages", [])
                    if not isinstance(msgs, list):
                        msgs = [msgs]
                    for msg in msgs:
                        if msg.__class__.__name__ == "AIMessage":
                            content = getattr(msg, "content", "")
                            if isinstance(content, str) and content:
                                output_parts.append(content)
                            elif isinstance(content, list):
                                for block in content:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        text = block.get("text", "")
                                        if text:
                                            output_parts.append(text)

            await self._agent_registry.update_status(task_id, "completed")
            return "\n".join(output_parts) or "(Agent completed with no text output)"

        except Exception as e:
            logger.exception("[AgentService] Agent %s failed", agent_name)
            await self._agent_registry.update_status(task_id, "error")
            raise
        finally:
            if agent is not None:
                try:
                    agent.close()
                except Exception:
                    pass

    async def _handle_task_output(self, task_id: str) -> str:
        """Get output of a background agent task."""
        running = self._tasks.get(task_id)
        if not running:
            return f"Error: task '{task_id}' not found"

        if not running.is_done:
            return json.dumps({
                "task_id": task_id,
                "status": "running",
                "message": "Agent is still running.",
            }, ensure_ascii=False)

        result = running.get_result()
        status = "error" if (result and result.startswith("<tool_use_error>")) else "completed"
        return json.dumps({
            "task_id": task_id,
            "status": status,
            "result": result,
        }, ensure_ascii=False)

    async def _handle_task_stop(self, task_id: str) -> str:
        """Stop a running background agent task."""
        running = self._tasks.get(task_id)
        if not running:
            return f"Error: task '{task_id}' not found"

        if running.is_done:
            return f"Task {task_id} already completed"

        running.task.cancel()
        await self._agent_registry.update_status(running.agent_id, "error")
        return f"Task {task_id} cancelled"
