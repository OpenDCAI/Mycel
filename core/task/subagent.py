"""Subagent runner for executing task agents."""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.tools import tool

from core.model_params import normalize_model_kwargs

from .types import AgentConfig, TaskParams, TaskResult


# Placeholder tool to ensure agent graph has a "tools" node.
#
# langchain's create_agent creates ToolNode only when:
#   available_tools = middleware_tools + regular_tools is non-empty
# where middleware_tools = [t for m in middleware for t in getattr(m, "tools", [])]
#
# Most middleware inject tools via wrap_model_call (dict schema), not self.tools.
# Only CommandMiddleware has self.tools (BaseTool instances).
# When subagent doesn't include CommandMiddleware, we need this placeholder.
@tool
def _placeholder_tool() -> str:
    """Internal placeholder - ensures ToolNode is created for middleware tools."""
    return ""


class SubagentRunner:
    """Execute subagent tasks with isolated tool sets."""

    def __init__(
        self,
        agents: dict[str, AgentConfig],
        parent_model: str,
        workspace_root: Path,
        api_key: str,
        model_kwargs: dict[str, Any] | None = None,
        queue_manager: Any = None,
        db_path: Path | None = None,
    ):
        self.agents = agents
        self.parent_model = parent_model
        self.workspace_root = workspace_root
        self.api_key = api_key
        self.model_kwargs = model_kwargs or {}
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._task_results: dict[str, TaskResult] = {}
        self._parent_runtime: Any = None
        self._queue_manager = queue_manager
        self.db_path = db_path

    def set_parent_runtime(self, runtime: Any) -> None:
        """Set parent runtime for background task event emission."""
        self._parent_runtime = runtime

    def _create_task_checkpointer(self) -> tuple[Any, None]:
        """Create an in-memory checkpointer for a sub-agent task.

        Sub-agents are short-lived (few turns) and don't need persistent state.
        Using MemorySaver avoids SQLite contention when multiple sub-agents
        run concurrently against the same leon.db file.

        Returns:
            (checkpointer, None) — no connection to close.
        """
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver(), None

    def _build_subagent_middleware(self, config: AgentConfig, all_middleware: list[Any]) -> list[Any]:
        """Build middleware stack for subagent based on allowed tools."""
        from core.command import CommandMiddleware
        from core.filesystem import FileSystemMiddleware
        from core.search import SearchMiddleware
        from core.web import WebMiddleware

        # Wildcard: inherit all parent middleware (General Agent = main Agent clone)
        if "*" in config.tools:
            return [mw for mw in all_middleware]

        # Tool name to middleware class mapping
        tool_middleware_map = {
            "read_file": FileSystemMiddleware,
            "write_file": FileSystemMiddleware,
            "edit_file": FileSystemMiddleware,
            "multi_edit": FileSystemMiddleware,
            "list_dir": FileSystemMiddleware,
            "Grep": SearchMiddleware,
            "Glob": SearchMiddleware,
            "run_command": CommandMiddleware,
            "command_status": CommandMiddleware,
            "web_search": WebMiddleware,
            "Fetch": WebMiddleware,
        }

        # Determine which middleware classes are needed
        needed_classes = set()
        for tool_name in config.tools:
            if tool_name in tool_middleware_map:
                needed_classes.add(tool_middleware_map[tool_name])

        # Filter middleware and configure enabled tools
        filtered_middleware = []
        for mw in all_middleware:
            mw_class = type(mw)

            if mw_class in needed_classes:
                # Clone middleware with filtered tools
                if mw_class == FileSystemMiddleware:
                    enabled = {
                        "read_file": "read_file" in config.tools,
                        "write_file": "write_file" in config.tools,
                        "edit_file": "edit_file" in config.tools,
                        "multi_edit": "multi_edit" in config.tools,
                        "list_dir": "list_dir" in config.tools,
                    }
                    new_mw = FileSystemMiddleware(
                        workspace_root=mw.workspace_root,
                        max_file_size=mw.max_file_size,
                        allowed_extensions=mw.allowed_extensions,
                        hooks=mw.hooks,
                        enabled_tools=enabled,
                        operation_recorder=getattr(mw, "operation_recorder", None),
                    )
                    filtered_middleware.append(new_mw)

                elif mw_class == SearchMiddleware:
                    new_mw = SearchMiddleware(
                        workspace_root=mw.workspace_root,
                        max_file_size=mw.max_file_size,
                        verbose=False,
                    )
                    filtered_middleware.append(new_mw)

                elif mw_class == CommandMiddleware:
                    enabled = {
                        "run_command": "run_command" in config.tools,
                        "command_status": "command_status" in config.tools,
                    }
                    new_mw = CommandMiddleware(
                        workspace_root=mw.workspace_root,
                        default_timeout=mw.default_timeout,
                        hooks=mw.hooks,
                        enabled_tools=enabled,
                    )
                    filtered_middleware.append(new_mw)

                elif mw_class == WebMiddleware:
                    enabled = {
                        "web_search": "web_search" in config.tools,
                        "Fetch": "Fetch" in config.tools,
                    }
                    new_mw = WebMiddleware(
                        tavily_api_key=getattr(mw, "_tavily_api_key", None),
                        exa_api_key=getattr(mw, "_exa_api_key", None),
                        firecrawl_api_key=getattr(mw, "_firecrawl_api_key", None),
                        jina_api_key=getattr(mw, "_jina_api_key", None),
                        max_search_results=mw.max_search_results,
                        timeout=mw.timeout,
                        enabled_tools=enabled,
                    )
                    filtered_middleware.append(new_mw)

        return filtered_middleware

    async def run(
        self,
        params: TaskParams,
        all_middleware: list[Any],
        parent_tool_call_id: str | None = None,
        parent_thread_id: str | None = None,
    ) -> TaskResult:
        """Run a subagent task."""
        task_id = str(uuid.uuid4())[:8]
        subagent_type = params["SubagentType"]

        config = self.agents.get(subagent_type)
        if not config:
            available = ", ".join(sorted(self.agents.keys()))
            return TaskResult(
                task_id=task_id,
                status="error",
                error=f"Unknown agent: {subagent_type}. Available: {available}",
            )

        # Determine model
        model_name = params.get("Model") or config.model or self.parent_model

        # Build model (unified path via init_chat_model)
        try:
            model_kwargs = normalize_model_kwargs(model_name, self.model_kwargs)
            model = init_chat_model(model_name, api_key=self.api_key, **model_kwargs)
        except Exception as e:
            return TaskResult(
                task_id=task_id,
                status="error",
                error=f"Failed to initialize model '{model_name}': {e}",
            )

        # Build filtered middleware
        middleware = self._build_subagent_middleware(config, all_middleware)

        # Build system prompt
        system_prompt = self._build_system_prompt(config)

        # Create subagent with unique thread_id
        subagent_thread_id = f"subagent_{task_id}"
        max_turns = params.get("MaxTurns")

        # Check if any middleware has self.tools (BaseTool instances).
        # Only need placeholder if no middleware has tools.
        middleware_has_tools = any(getattr(m, "tools", None) for m in middleware)
        tools = [] if middleware_has_tools else [_placeholder_tool]

        # In-memory checkpointer — no SQLite contention
        checkpointer, _ = self._create_task_checkpointer()

        try:
            agent = create_agent(
                model=model,
                tools=tools,
                system_prompt=system_prompt,
                middleware=middleware,
                checkpointer=checkpointer,
            )
        except Exception as e:
            return TaskResult(
                task_id=task_id,
                status="error",
                error=f"Failed to create subagent: {e}",
            )

        # Execute
        prompt = params["Prompt"]
        description = params.get("Description", "")

        if params.get("RunInBackground"):
            task = asyncio.create_task(
                self._execute_agent(agent, prompt, subagent_thread_id, max_turns, task_id, parent_thread_id, description, parent_tool_call_id)
            )
            self._active_tasks[task_id] = task
            return TaskResult(
                task_id=task_id,
                thread_id=subagent_thread_id,
                status="running",
                description=description or None,
                result=f"Task started in background. Use TaskOutput with TaskId='{task_id}' to get results.",
            )
        else:
            return await self._execute_agent(agent, prompt, subagent_thread_id, max_turns, task_id, description=description)

    async def run_streaming(
        self,
        params: TaskParams,
        all_middleware: list[Any],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Run a subagent task with streaming output."""
        task_id = str(uuid.uuid4())[:8]
        subagent_type = params["SubagentType"]

        config = self.agents.get(subagent_type)
        if not config:
            available = ", ".join(sorted(self.agents.keys()))
            yield {
                "event": "task_error",
                "data": json.dumps(
                    {
                        "task_id": task_id,
                        "error": f"Unknown agent: {subagent_type}. Available: {available}",
                    }
                ),
            }
            return

        # Emit task start event
        yield {
            "event": "task_start",
            "data": json.dumps(
                {
                    "task_id": task_id,
                    "thread_id": f"subagent_{task_id}",
                    "subagent_type": subagent_type,
                    "description": params.get("Description", ""),
                }
            ),
        }

        # Determine model
        model_name = params.get("Model") or config.model or self.parent_model

        # Build model
        try:
            model_kwargs = normalize_model_kwargs(model_name, self.model_kwargs)
            model = init_chat_model(model_name, api_key=self.api_key, **model_kwargs)
        except Exception as e:
            yield {
                "event": "task_error",
                "data": json.dumps({"task_id": task_id, "error": f"Failed to initialize model '{model_name}': {e}"}),
            }
            return

        # Build filtered middleware
        middleware = self._build_subagent_middleware(config, all_middleware)

        # Build system prompt
        system_prompt = self._build_system_prompt(config)

        # Create subagent with unique thread_id
        subagent_thread_id = f"subagent_{task_id}"
        max_turns = params.get("MaxTurns")

        # Check if any middleware has self.tools
        middleware_has_tools = any(getattr(m, "tools", None) for m in middleware)
        tools = [] if middleware_has_tools else [_placeholder_tool]

        # In-memory checkpointer — no SQLite contention
        checkpointer, _ = self._create_task_checkpointer()

        try:
            agent = create_agent(
                model=model,
                tools=tools,
                system_prompt=system_prompt,
                middleware=middleware,
                checkpointer=checkpointer,
            )
        except Exception as e:
            yield {
                "event": "task_error",
                "data": json.dumps({"task_id": task_id, "error": f"Failed to create subagent: {e}"}),
            }
            return

        # Execute with streaming
        prompt = params["Prompt"]
        turns_used = 0
        emitted_tool_call_ids: set[str] = set()
        text_parts: list[str] = []
        max_text_chars = 200_000

        try:
            async for chunk in agent.astream(
                {"messages": [{"role": "user", "content": prompt}]},
                config={"configurable": {"thread_id": subagent_thread_id}},
                stream_mode=["messages", "updates"],
            ):
                if not chunk or not isinstance(chunk, tuple) or len(chunk) != 2:
                    continue

                mode, data = chunk

                # Token-level streaming from "messages" mode
                if mode == "messages":
                    msg_chunk, metadata = data
                    msg_class = msg_chunk.__class__.__name__
                    if msg_class == "AIMessageChunk":
                        content = self._extract_text_content(getattr(msg_chunk, "content", ""))
                        if content:
                            if sum(len(p) for p in text_parts) < max_text_chars:
                                remaining = max_text_chars - sum(len(p) for p in text_parts)
                                text_parts.append(content[:remaining])
                            yield {
                                "event": "task_text",
                                "data": json.dumps({"task_id": task_id, "content": content}),
                            }

                # Node-level updates from "updates" mode
                elif mode == "updates":
                    if not isinstance(data, dict):
                        continue
                    for _node_name, node_update in data.items():
                        if not isinstance(node_update, dict):
                            continue
                        messages = node_update.get("messages", [])
                        if not isinstance(messages, list):
                            messages = [messages]
                        for msg in messages:
                            msg_class = msg.__class__.__name__
                            if msg_class == "AIMessage":
                                for tc in getattr(msg, "tool_calls", []):
                                    tc_id = tc.get("id")
                                    if tc_id and tc_id in emitted_tool_call_ids:
                                        continue
                                    if tc_id:
                                        emitted_tool_call_ids.add(tc_id)
                                    yield {
                                        "event": "task_tool_call",
                                        "data": json.dumps(
                                            {
                                                "task_id": task_id,
                                                "id": tc.get("id"),
                                                "name": tc.get("name", "unknown"),
                                                "args": tc.get("args", {}),
                                            }
                                        ),
                                    }
                            elif msg_class == "ToolMessage":
                                yield {
                                    "event": "task_tool_result",
                                    "data": json.dumps(
                                        {
                                            "task_id": task_id,
                                            "tool_call_id": getattr(msg, "tool_call_id", None),
                                            "name": getattr(msg, "name", "unknown"),
                                            "content": str(getattr(msg, "content", "")),
                                        }
                                    ),
                                }

            # Task completed
            final_text = "".join(text_parts).strip() or None
            desc = params.get("Description") or None
            self._task_results[task_id] = TaskResult(
                task_id=task_id,
                thread_id=subagent_thread_id,
                status="completed",
                result=final_text,
                description=desc,
                turns_used=turns_used,
            )
            yield {
                "event": "task_done",
                "data": json.dumps(
                    {
                        "task_id": task_id,
                        "thread_id": subagent_thread_id,
                        "status": "completed",
                    }
                ),
            }

        except Exception as e:
            desc = params.get("Description") or None
            self._task_results[task_id] = TaskResult(
                task_id=task_id,
                thread_id=subagent_thread_id,
                status="error",
                error=str(e),
                description=desc,
                turns_used=turns_used,
            )
            yield {
                "event": "task_error",
                "data": json.dumps({"task_id": task_id, "error": str(e)}),
            }

    def _extract_text_content(self, raw_content: Any) -> str:
        """Extract text content from message content."""
        if isinstance(raw_content, str):
            return raw_content
        if isinstance(raw_content, list):
            parts: list[str] = []
            for block in raw_content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            return "".join(parts)
        return str(raw_content)

    async def _execute_agent(
        self,
        agent: Any,
        prompt: str,
        thread_id: str,
        max_turns: int,
        task_id: str,
        parent_thread_id: str | None = None,
        description: str = "",
        parent_tool_call_id: str | None = None,
    ) -> TaskResult:
        """Execute agent and return result.

        When a parent runtime is available, uses astream() to emit real-time
        background_task_* events. Otherwise falls back to ainvoke().
        """
        runtime = self._parent_runtime
        if runtime:
            result = await self._execute_agent_streaming(agent, prompt, thread_id, task_id, runtime, description, parent_tool_call_id)
        else:
            result = await self._execute_agent_invoke(agent, prompt, thread_id, task_id, description)

        # Inject completion notification into parent's unified queue.
        # This may trigger new_run (via wake handler) when parent is idle.
        if parent_thread_id and result.status in ("completed", "error"):
            self._inject_task_notification(task_id, result, parent_thread_id)

        # Emit background_task_done/error AFTER notification injection.
        # This ensures new_run arrives before background_task_done on the
        # activity SSE, preventing premature frontend disconnect.
        if runtime and result.status in ("completed", "error"):
            event_name = "background_task_done" if result.status == "completed" else "background_task_error"
            event_data: dict[str, Any] = {"task_id": task_id, "status": result.status}
            if result.status == "error":
                event_data["error"] = result.error or ""
            runtime.emit_activity_event({
                "event": event_name,
                "data": json.dumps(event_data),
            })

        return result

    def _inject_task_notification(
        self, task_id: str, result: TaskResult, parent_thread_id: str
    ) -> None:
        """Enqueue task notification into unified SQLite queue.

        The wake handler (registered by the host) will trigger a new run if
        the agent is IDLE. If the agent is ACTIVE, before_model will drain
        the message on the next LLM cycle.
        """
        from core.queue import format_task_notification

        summary = (result.result or "")[:200] if result.status == "completed" else (result.error or "")
        xml = format_task_notification(
            task_id=task_id,
            status=result.status,
            summary=summary,
            result=result.result,
            description=result.description,
        )
        if self._queue_manager:
            self._queue_manager.enqueue(xml, parent_thread_id)
        else:
            import logging
            logging.getLogger(__name__).warning(
                "_inject_task_notification: no queue_manager for thread %s", parent_thread_id
            )

    async def _execute_agent_invoke(
        self,
        agent: Any,
        prompt: str,
        thread_id: str,
        task_id: str,
        description: str = "",
    ) -> TaskResult:
        """Fallback execution via ainvoke (no event emission)."""
        turns_used = 0
        desc = description or None
        try:
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": prompt}]},
                config={"configurable": {"thread_id": thread_id}},
            )

            messages = result.get("messages", [])
            if messages:
                last_message = messages[-1]
                content = last_message.content if hasattr(last_message, "content") else str(last_message)
            else:
                content = "No response generated."

            turns_used = len([m for m in messages if hasattr(m, "role")])

            task_result = TaskResult(
                task_id=task_id,
                thread_id=thread_id,
                status="completed",
                result=content,
                description=desc,
                turns_used=turns_used,
            )

        except Exception as e:
            task_result = TaskResult(
                task_id=task_id,
                thread_id=thread_id,
                status="error",
                error=str(e),
                description=desc,
                turns_used=turns_used,
            )

        self._task_results[task_id] = task_result
        return task_result

    async def _execute_agent_streaming(
        self,
        agent: Any,
        prompt: str,
        thread_id: str,
        task_id: str,
        runtime: Any,
        description: str = "",
        parent_tool_call_id: str | None = None,
    ) -> TaskResult:
        """Streaming execution that emits background_task_* events via runtime.

        When parent_tool_call_id is provided, also emits subagent_task_* events
        so the frontend AgentsView can track real-time progress.
        """
        start_data: dict[str, Any] = {"task_id": task_id, "thread_id": thread_id}
        if description:
            start_data["description"] = description
        runtime.emit_activity_event({
            "event": "background_task_start",
            "data": json.dumps(start_data),
        })
        # Also emit subagent event for AgentsView real-time tracking
        if parent_tool_call_id:
            runtime.emit_subagent_event(parent_tool_call_id, {
                "event": "task_start",
                "data": json.dumps(start_data),
            })

        text_parts: list[str] = []
        max_text_chars = 200_000
        emitted_tool_call_ids: set[str] = set()

        try:
            async for chunk in agent.astream(
                {"messages": [{"role": "user", "content": prompt}]},
                config={"configurable": {"thread_id": thread_id}},
                stream_mode=["messages", "updates"],
            ):
                if not chunk or not isinstance(chunk, tuple) or len(chunk) != 2:
                    continue

                mode, data = chunk

                if mode == "messages":
                    msg_chunk, _metadata = data
                    if msg_chunk.__class__.__name__ == "AIMessageChunk":
                        content = self._extract_text_content(getattr(msg_chunk, "content", ""))
                        if content:
                            if sum(len(p) for p in text_parts) < max_text_chars:
                                remaining = max_text_chars - sum(len(p) for p in text_parts)
                                text_parts.append(content[:remaining])
                            runtime.emit_activity_event({
                                "event": "background_task_text",
                                "data": json.dumps({"task_id": task_id, "content": content}),
                            })
                            if parent_tool_call_id:
                                runtime.emit_subagent_event(parent_tool_call_id, {
                                    "event": "task_text",
                                    "data": json.dumps({"task_id": task_id, "content": content}),
                                })

                elif mode == "updates":
                    if not isinstance(data, dict):
                        continue
                    for _node_name, node_update in data.items():
                        if not isinstance(node_update, dict):
                            continue
                        messages = node_update.get("messages", [])
                        if not isinstance(messages, list):
                            messages = [messages]
                        for msg in messages:
                            msg_class = msg.__class__.__name__
                            if msg_class == "AIMessage":
                                for tc in getattr(msg, "tool_calls", []):
                                    tc_id = tc.get("id")
                                    if tc_id and tc_id in emitted_tool_call_ids:
                                        continue
                                    if tc_id:
                                        emitted_tool_call_ids.add(tc_id)
                                    tc_data = {
                                        "task_id": task_id,
                                        "id": tc_id,
                                        "name": tc.get("name", "unknown"),
                                        "args": tc.get("args", {}),
                                    }
                                    if parent_tool_call_id:
                                        runtime.emit_subagent_event(parent_tool_call_id, {
                                            "event": "task_tool_call",
                                            "data": json.dumps(tc_data),
                                        })
                            elif msg_class == "ToolMessage":
                                tr_data = {
                                    "task_id": task_id,
                                    "tool_call_id": getattr(msg, "tool_call_id", None),
                                    "name": getattr(msg, "name", "unknown"),
                                    "content": str(getattr(msg, "content", "")),
                                }
                                if parent_tool_call_id:
                                    runtime.emit_subagent_event(parent_tool_call_id, {
                                        "event": "task_tool_result",
                                        "data": json.dumps(tr_data),
                                    })

            final_text = "".join(text_parts).strip() or None
            desc = description or None
            task_result = TaskResult(
                task_id=task_id,
                thread_id=thread_id,
                status="completed",
                result=final_text,
                description=desc,
            )
            # NOTE: background_task_done is emitted by _execute_agent (the caller)
            # AFTER _inject_task_notification, so that new_run arrives before
            # background_task_done on the activity SSE — preventing premature disconnect.
            if parent_tool_call_id:
                runtime.emit_subagent_event(parent_tool_call_id, {
                    "event": "task_done",
                    "data": json.dumps({"task_id": task_id, "status": "completed"}),
                })

        except Exception as e:
            desc = description or None
            task_result = TaskResult(
                task_id=task_id,
                thread_id=thread_id,
                status="error",
                error=str(e),
                description=desc,
            )
            # NOTE: background_task_error is emitted by _execute_agent (the caller)
            if parent_tool_call_id:
                runtime.emit_subagent_event(parent_tool_call_id, {
                    "event": "task_error",
                    "data": json.dumps({"task_id": task_id, "error": str(e)}),
                })

        self._task_results[task_id] = task_result
        return task_result

    def _build_system_prompt(self, config: AgentConfig) -> str:
        """Build system prompt for subagent."""
        # Wildcard agent: don't list tools (inherits all)
        if "*" in config.tools:
            return f"""You are a sub-agent: {config.name}

{config.system_prompt}

**Context:**
- Workspace: `{self.workspace_root}`

**Important Rules:**
1. All file paths must be absolute paths.
2. File operations are restricted to the workspace.
3. Complete your task efficiently and report your findings.
"""

        # Regular agent: list available tools
        prompt = f"""You are a specialized sub-agent: {config.name}

{config.system_prompt}

**Context:**
- Workspace: `{self.workspace_root}`
- Available tools: {", ".join(config.tools)}

**Important Rules:**
1. All file paths must be absolute paths.
2. File operations are restricted to the workspace.
3. Complete your task efficiently and report your findings.
"""
        return prompt

    def get_task_status(self, task_id: str) -> TaskResult:
        """Get status of a background task."""
        # Check if completed
        if task_id in self._task_results:
            return self._task_results[task_id]

        # Check if still running
        if task_id in self._active_tasks:
            task = self._active_tasks[task_id]
            if task.done():
                try:
                    return task.result()
                except Exception as e:
                    return TaskResult(
                        task_id=task_id,
                        status="error",
                        error=str(e),
                    )
            else:
                return TaskResult(
                    task_id=task_id,
                    status="running",
                    result="Task is still running...",
                )

        return TaskResult(
            task_id=task_id,
            status="error",
            error=f"Unknown task_id: {task_id}",
        )
