"""
Task Middleware - Sub-agent orchestration

Tools:
- Task: Launch specialized sub-agents for complex tasks
- TaskOutput: Get output from background tasks

Sub-agents are defined in .md files with YAML frontmatter.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain_core.messages import ToolMessage

from .loader import AgentLoader
from .subagent import SubagentRunner
from .types import TaskParams, TaskResult


class TaskMiddleware(AgentMiddleware):
    """
    Task Middleware - Orchestrate specialized sub-agents

    Features:
    - File-driven agent definitions (.md with YAML frontmatter)
    - Three-level priority: project > user > built-in
    - Selective tool inheritance from parent agent
    - Background task execution support
    """

    TOOL_TASK = "Task"
    TOOL_TASK_OUTPUT = "TaskOutput"

    def __init__(
        self,
        workspace_root: str | Path,
        parent_model: str,
        api_key: str | None = None,
        model_kwargs: dict[str, Any] | None = None,
        parent_middleware: list[Any] | None = None,
        db_path: Path | None = None,
        queue_manager: Any = None,
        verbose: bool = True,
    ):
        """
        Initialize Task middleware.

        Args:
            workspace_root: Workspace directory
            parent_model: Parent agent's model name
            api_key: API key for sub-agents
            model_kwargs: Model kwargs to pass to init_chat_model (base_url, model_provider, etc.)
            parent_middleware: Parent agent's middleware stack (for tool inheritance)
            db_path: Path to SQLite DB for per-task checkpointer connections
            queue_manager: Shared MessageQueueManager instance
            verbose: Whether to output detailed logs
        """
        self.workspace_root = Path(workspace_root).resolve()
        self.parent_model = parent_model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        self.model_kwargs = model_kwargs or {}
        self.parent_middleware = parent_middleware or []
        self.db_path = db_path
        self.verbose = verbose
        self.agent = None  # Will be set by parent agent

        # Load agents from all sources
        self.loader = AgentLoader(self.workspace_root)
        self.agents = self.loader.load_all_agents()

        # Initialize runner
        self.runner = SubagentRunner(
            agents=self.agents,
            parent_model=self.parent_model,
            workspace_root=self.workspace_root,
            api_key=self.api_key,
            model_kwargs=self.model_kwargs,
            queue_manager=queue_manager,
            db_path=db_path,
        )

        if self.verbose:
            if self.agents:
                print(f"[TaskMiddleware] Loaded {len(self.agents)} agents: {', '.join(sorted(self.agents.keys()))}")
            else:
                print("[TaskMiddleware] No agents loaded")

    def _get_tool_schemas(self) -> list[dict]:
        """Get task tool schemas with dynamic agent enum."""
        agent_names = sorted(self.agents.keys())

        if not agent_names:
            return []

        # Build agent descriptions for enum
        agent_descriptions = []
        for name in agent_names:
            config = self.agents[name]
            agent_descriptions.append(f"- {name}: {config.description}")

        return [
            {
                "type": "function",
                "function": {
                    "name": self.TOOL_TASK,
                    "description": f"""Launch a specialized sub-agent to handle a task autonomously.

Available agents:
{chr(10).join(agent_descriptions)}

Each agent has specific tools and capabilities. Choose the appropriate agent for your task.
The agent will work independently and return results when complete.""",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "SubagentType": {
                                "type": "string",
                                "enum": agent_names,
                                "description": "The type of sub-agent to launch",
                            },
                            "Prompt": {
                                "type": "string",
                                "description": "The task description for the sub-agent",
                            },
                            "Description": {
                                "type": "string",
                                "description": "3-5 word summary of the task",
                            },
                            "Model": {
                                "type": "string",
                                "description": "Optional model override (defaults to agent's configured model)",
                            },
                            "RunInBackground": {
                                "type": "boolean",
                                "description": "Run in background (use TaskOutput to check progress)",
                            },
                            "MaxTurns": {
                                "type": "integer",
                                "description": "Maximum number of turns for the sub-agent",
                            },
                            "Resume": {
                                "type": "string",
                                "description": "Agent ID to resume from previous execution",
                            },
                        },
                        "required": ["SubagentType", "Prompt", "Description"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": self.TOOL_TASK_OUTPUT,
                    "description": "Get output from a running or completed background task. Use block=true to wait for completion.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "TaskId": {
                                "type": "string",
                                "description": "The task ID returned from a background task",
                            },
                            "Block": {
                                "type": "boolean",
                                "description": "Whether to wait for task completion (default: true)",
                            },
                            "Timeout": {
                                "type": "number",
                                "description": "Max wait time in ms (max 600000)",
                            },
                        },
                        "required": ["TaskId"],
                    },
                },
            },
        ]

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Inject task tool definitions."""
        if not self.agents:
            return handler(request)

        tools = list(request.tools or [])
        tools.extend(self._get_tool_schemas())
        return handler(request.override(tools=tools))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """Inject task tool definitions (async)."""
        if not self.agents:
            return await handler(request)

        tools = list(request.tools or [])
        tools.extend(self._get_tool_schemas())
        return await handler(request.override(tools=tools))

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        """Handle task tool calls (sync wrapper for async)."""
        tool_call = request.tool_call
        tool_name = tool_call.get("name")

        if tool_name not in (self.TOOL_TASK, self.TOOL_TASK_OUTPUT):
            return handler(request)

        parent_thread_id = request.runtime.config.get("configurable", {}).get("thread_id")

        # Run async handler in sync context
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self._handle_tool_call(tool_call, parent_thread_id))

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        """Handle task tool calls (async)."""
        tool_call = request.tool_call
        tool_name = tool_call.get("name")

        if tool_name not in (self.TOOL_TASK, self.TOOL_TASK_OUTPUT):
            return await handler(request)

        parent_thread_id = request.runtime.config.get("configurable", {}).get("thread_id")
        return await self._handle_tool_call(tool_call, parent_thread_id)

    async def _handle_tool_call(self, tool_call: dict, parent_thread_id: str | None = None) -> ToolMessage:
        """Handle task or task_status tool call."""
        tool_name = tool_call.get("name")
        tool_id = tool_call.get("id", "")
        args = tool_call.get("args", {})

        if tool_name == self.TOOL_TASK:
            result = await self._handle_task(args, tool_id, parent_thread_id)
        elif tool_name == self.TOOL_TASK_OUTPUT:
            result = await self._handle_task_output(args)
        else:
            result = TaskResult(
                task_id="",
                status="error",
                error=f"Unknown tool: {tool_name}",
            )

        return self._make_tool_message(result, tool_id)

    async def _handle_task(self, args: dict, tool_id: str, parent_thread_id: str | None = None) -> TaskResult:
        """Handle task tool call.

        - Background mode: start an async task and return immediately (TaskOutput polls).
        - Foreground mode: stream sub-agent progress events and return final output.
        """
        params: TaskParams = {
            "SubagentType": args.get("SubagentType", ""),
            "Prompt": args.get("Prompt", ""),
        }

        if "Description" in args:
            params["Description"] = args["Description"]
        if "Model" in args:
            params["Model"] = args["Model"]
        if "RunInBackground" in args:
            params["RunInBackground"] = args["RunInBackground"]
        if "MaxTurns" in args:
            params["MaxTurns"] = args["MaxTurns"]
        if "Resume" in args:
            params["Resume"] = args["Resume"]

        if params.get("RunInBackground"):
            # Background execution uses runner.run() which registers task_id for TaskOutput.
            return await self.runner.run(
                params=params,
                all_middleware=self.parent_middleware,
                parent_tool_call_id=tool_id,
                parent_thread_id=parent_thread_id,
            )

        # Foreground: use streaming mode to capture sub-agent events
        task_id = None
        thread_id = None
        final_result = None
        final_status = "completed"
        final_error = None
        turns_used = 0

        text_parts: list[str] = []
        async for event in self.runner.run_streaming(
            params=params,
            all_middleware=self.parent_middleware,
        ):
            # Extract task_id and thread_id from task_start
            if event["event"] == "task_start":
                import json

                data = json.loads(event["data"])
                task_id = data["task_id"]
                thread_id = data.get("thread_id", f"subagent_{task_id}")

            # Forward all sub-agent events to agent runtime
            if hasattr(self, "agent") and hasattr(self.agent, "runtime"):
                self.agent.runtime.emit_subagent_event(tool_id, event)

            # Capture final result
            if event["event"] == "task_done":
                import json

                data = json.loads(event["data"])
                final_status = data.get("status", "completed")
            elif event["event"] == "task_error":
                import json

                data = json.loads(event["data"])
                final_error = data.get("error", "Unknown error")
                final_status = "error"
            elif event["event"] == "task_text":
                import json

                data = json.loads(event["data"])
                chunk = data.get("content") or ""
                if chunk:
                    text_parts.append(chunk)

        final_result = "".join(text_parts).strip() or final_result

        # Get the final result from the runner's task results (streaming path must populate it).
        if task_id:
            result = self.runner.get_task_status(task_id)
            return result

        # Fallback if task_id was not captured
        return TaskResult(
            task_id=task_id or "",
            thread_id=thread_id,
            status=final_status,
            result=final_result,
            error=final_error,
            turns_used=turns_used,
        )

    def _handle_task_status(self, args: dict) -> TaskResult:
        """Handle task_status tool call."""
        task_id = args.get("TaskId", "")
        return self.runner.get_task_status(task_id)

    async def _handle_task_output(self, args: dict) -> TaskResult:
        """Handle TaskOutput tool call.

        Note: Block parameter is ignored. TaskOutput always returns current status.
        If task is still running, agent should wait for task-notification to trigger
        next turn, then call TaskOutput again to get final result.
        """
        task_id = args.get("TaskId", "")
        # Block parameter is ignored - always return current status
        return self.runner.get_task_status(task_id)

    def _make_tool_message(self, result: TaskResult, tool_id: str) -> ToolMessage:
        """Create tool message from result."""
        if result.status == "error":
            content = f"Error: {result.error}"
        elif result.status == "running":
            content = f"Task {result.task_id} is running.\n{result.result or ''}"
        else:
            content = result.result or "Task completed."

        metadata: dict[str, str] = {}
        if result.task_id:
            metadata["task_id"] = result.task_id
        if result.thread_id:
            metadata["subagent_thread_id"] = result.thread_id
        if result.description:
            metadata["description"] = result.description

        return ToolMessage(content=content, tool_call_id=tool_id, metadata=metadata)

    def set_parent_middleware(self, middleware: list[Any]) -> None:
        """Set parent middleware after initialization."""
        self.parent_middleware = middleware

    def set_db_path(self, db_path: Path) -> None:
        """Set database path for per-task checkpointer connections."""
        self.db_path = db_path
        self.runner.db_path = db_path

    def set_agent(self, agent: Any) -> None:
        """Set parent agent reference for runtime access."""
        self.agent = agent
        if hasattr(agent, "runtime"):
            self.runner.set_parent_runtime(agent.runtime)

    async def run_task_streaming(self, params: TaskParams):
        """Run a task with streaming output. Returns async generator for SSE."""
        return self.runner.run_streaming(
            params=params,
            all_middleware=self.parent_middleware,
        )
