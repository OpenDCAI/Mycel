"""AgentService - Registers Agent/TaskOutput/TaskStop tools into ToolRegistry.

Creates independent LeonAgent instances per spawn. Sub-agents run as asyncio
tasks; parent blocks until completion by default. `run_in_background=True`
fires-and-forgets and returns a task_id for polling via TaskOutput.
Backed by AgentRegistry (SQLite).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from core.agents.registry import AgentEntry, AgentRegistry
from core.runtime.middleware.queue.formatters import format_background_notification
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
                "description": (
                    "Short description of what agent will do. Required when run_in_background is true; "
                    "shown in the background task indicator."
                ),
            },
            "run_in_background": {
                "type": "boolean",
                "default": False,
                "description": "Fire-and-forget: return immediately with task_id instead of waiting for completion",
            },
            "max_turns": {
                "type": "integer",
                "description": "Maximum turns the agent can take",
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
    """Tracks a background asyncio.Task (agent run) with its metadata."""

    def __init__(self, task: asyncio.Task, agent_id: str, thread_id: str, description: str = ""):
        self.task = task
        self.agent_id = agent_id
        self.thread_id = thread_id
        self.description = description

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


class _BashBackgroundRun:
    """Wraps AsyncCommand to provide the same is_done/get_result interface as _RunningTask."""

    def __init__(self, async_cmd: Any, command: str, description: str = ""):
        self._cmd = async_cmd
        self.command = command
        self.description = description

    @property
    def is_done(self) -> bool:
        return bool(self._cmd.done)

    def get_result(self) -> str | None:
        if not self._cmd.done:
            return None
        stdout = "".join(self._cmd.stdout_buffer)
        stderr = "".join(self._cmd.stderr_buffer)
        exit_code = self._cmd.exit_code
        parts = []
        if stdout:
            parts.append(stdout)
        if stderr:
            parts.append(f"[stderr]\n{stderr}")
        if exit_code is not None and exit_code != 0:
            parts.append(f"[exit_code: {exit_code}]")
        return "\n".join(parts) if parts else "(completed with no output)"


# Type alias for the shared background run registry
BackgroundRun = _RunningTask | _BashBackgroundRun


class AgentService:
    """Registers Agent, TaskOutput, TaskStop tools into ToolRegistry.

    Creates independent LeonAgent instances for each spawn. By default the
    parent blocks until the sub-agent completes (blocking tool call that does
    NOT block the frontend event loop). Set run_in_background=True for true
    fire-and-forget behaviour.

    The shared_runs dict (optional) allows CommandService to register bash
    background runs so that TaskOutput/TaskStop can retrieve them too.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        agent_registry: AgentRegistry,
        workspace_root: Path,
        model_name: str,
        queue_manager: Any | None = None,
        shared_runs: dict[str, BackgroundRun] | None = None,
    ):
        self._agent_registry = agent_registry
        self._workspace_root = workspace_root
        self._model_name = model_name
        self._queue_manager = queue_manager
        # Shared with CommandService so TaskOutput covers both bash and agent runs.
        self._tasks: dict[str, BackgroundRun] = shared_runs if shared_runs is not None else {}

        tool_registry.register(
            ToolEntry(
                name="Agent",
                mode=ToolMode.INLINE,
                schema=AGENT_SCHEMA,
                handler=self._handle_agent,
                source="AgentService",
            )
        )
        tool_registry.register(
            ToolEntry(
                name="TaskOutput",
                mode=ToolMode.INLINE,
                schema=TASK_OUTPUT_SCHEMA,
                handler=self._handle_task_output,
                source="AgentService",
            )
        )
        tool_registry.register(
            ToolEntry(
                name="TaskStop",
                mode=ToolMode.INLINE,
                schema=TASK_STOP_SCHEMA,
                handler=self._handle_task_stop,
                source="AgentService",
            )
        )

    async def _handle_agent(
        self,
        prompt: str,
        subagent_type: str = "General",
        name: str | None = None,
        description: str | None = None,
        run_in_background: bool = False,
        max_turns: int | None = None,
    ) -> str:
        """Spawn an independent LeonAgent and run it with the given prompt."""
        from sandbox.thread_context import get_current_thread_id

        task_id = uuid.uuid4().hex[:8]
        agent_name = name or f"agent-{task_id}"
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
            self._run_agent(
                task_id,
                agent_name,
                thread_id,
                prompt,
                subagent_type,
                max_turns,
                description=description or "",
                run_in_background=run_in_background,
            )
        )
        if run_in_background:
            # True fire-and-forget: track in self._tasks for TaskOutput/TaskStop
            running = _RunningTask(task=task, agent_id=task_id, thread_id=thread_id, description=description or "")
            self._tasks[task_id] = running
            return json.dumps(
                {
                    "task_id": task_id,
                    "agent_name": agent_name,
                    "thread_id": thread_id,
                    "status": "running",
                    "message": "Agent started in background. Use TaskOutput to get result.",
                },
                ensure_ascii=False,
            )

        # Default: parent blocks until sub-agent completes (does not block frontend event loop)
        try:
            result = await task
            await self._agent_registry.update_status(task_id, "completed")
            return result
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
        description: str = "",
        run_in_background: bool = False,
    ) -> str:
        """Create and run an independent LeonAgent, collect its text output."""
        # Isolate this sub-agent from the parent's LangChain callback chain.
        # asyncio.create_task() copies the current context, so this task inherits
        # var_child_runnable_config which carries the parent graph's inheritable
        # callbacks (including StreamMessagesHandler for stream_mode="messages").
        # Without isolation, the sub-agent's LLM calls would write tokens directly
        # into the parent's "messages" stream. We clear it here so the sub-agent
        # starts a fresh, independent callback context.
        from langchain_core.runnables.config import var_child_runnable_config

        var_child_runnable_config.set(None)

        # Lazy import avoids circular dependency (agent.py imports AgentService)
        from core.runtime.agent import create_leon_agent
        from sandbox.thread_context import get_current_thread_id, set_current_thread_id

        parent_thread_id = get_current_thread_id()

        # emit_fn is set if EventBus is available; used for task lifecycle SSE events
        emit_fn = None
        try:
            from backend.web.event_bus import get_event_bus

            event_bus = get_event_bus()
            emit_fn = event_bus.make_emitter(
                thread_id=parent_thread_id,
                agent_id=task_id,
                agent_name=agent_name,
            )
        except ImportError:
            pass  # backend not available in standalone core usage

        agent = None
        try:
            agent = create_leon_agent(
                model_name=self._model_name,
                workspace_root=self._workspace_root,
                verbose=False,
            )
            # In async context LeonAgent defers checkpointer init; call ainit() to
            # ensure state is persisted (and loadable via GET /api/threads/{thread_id}).
            await agent.ainit()

            # Wire child agent events to the parent's EventBus subscription
            # so the parent SSE stream shows sub-agent activity.
            if emit_fn is not None:
                if hasattr(agent, "runtime") and hasattr(agent.runtime, "bind_thread"):
                    agent.runtime.bind_thread(activity_sink=emit_fn)

            set_current_thread_id(thread_id)

            # Notify frontend: task started
            if emit_fn is not None:
                await emit_fn(
                    {
                        "event": "task_start",
                        "data": json.dumps(
                            {
                                "task_id": task_id,
                                "thread_id": thread_id,
                                "background": run_in_background,
                                "task_type": "agent",
                                "description": description or agent_name,
                            },
                            ensure_ascii=False,
                        ),
                    }
                )

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
            result = "\n".join(output_parts) or "(Agent completed with no text output)"
            # Notify frontend: task done
            if emit_fn is not None:
                await emit_fn(
                    {
                        "event": "task_done",
                        "data": json.dumps(
                            {
                                "task_id": task_id,
                                "background": run_in_background,
                            },
                            ensure_ascii=False,
                        ),
                    }
                )
            # Queue notification only for background runs — blocking callers already
            # received the result as the tool's return value; sending a notification
            # would trigger a spurious new parent turn.
            if run_in_background and self._queue_manager and parent_thread_id:
                label = description or agent_name
                notification = format_background_notification(
                    task_id=task_id,
                    status="completed",
                    summary=label,
                    description=label,
                )
                self._queue_manager.enqueue(notification, parent_thread_id, notification_type="agent")
            return result

        except Exception:
            logger.exception("[AgentService] Agent %s failed", agent_name)
            await self._agent_registry.update_status(task_id, "error")
            # Notify frontend: task error
            if emit_fn is not None:
                try:
                    await emit_fn(
                        {
                            "event": "task_error",
                            "data": json.dumps(
                                {
                                    "task_id": task_id,
                                    "background": run_in_background,
                                },
                                ensure_ascii=False,
                            ),
                        }
                    )
                except Exception:
                    pass
            if run_in_background and self._queue_manager and parent_thread_id:
                label = description or agent_name
                notification = format_background_notification(
                    task_id=task_id,
                    status="error",
                    summary=label,
                    description=label,
                )
                self._queue_manager.enqueue(notification, parent_thread_id, notification_type="agent")
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
            return json.dumps(
                {
                    "task_id": task_id,
                    "status": "running",
                    "message": "Agent is still running.",
                },
                ensure_ascii=False,
            )

        result = running.get_result()
        status = "error" if (result and result.startswith("<tool_use_error>")) else "completed"
        return json.dumps(
            {
                "task_id": task_id,
                "status": status,
                "result": result,
            },
            ensure_ascii=False,
        )

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
