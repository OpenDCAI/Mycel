"""
TaskBoard Middleware — Agent tools for panel_tasks board management.

Tools:
- ListBoardTasks: List tasks with optional status/priority filter
- ClaimTask: Claim a task (set running + thread_id + started_at)
- UpdateTaskProgress: Update progress and optionally append a note
- CompleteTask: Mark task completed with result
- FailTask: Mark task failed with reason
- CreateBoardTask: Create a new board task with source="agent"
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain_core.messages import ToolMessage
from langchain_core.messages.tool import ToolCall

from backend.taskboard._service_loader import require_task_service

logger = logging.getLogger(__name__)


class TaskBoardMiddleware(AgentMiddleware):
    """
    Middleware that gives agents tools to interact with the panel_tasks board.

    Agents can list, claim, update, complete, fail, and create board tasks.
    All operations go through task_service (sync SQLite CRUD).
    """

    TOOL_LIST = "ListBoardTasks"
    TOOL_CLAIM = "ClaimTask"
    TOOL_PROGRESS = "UpdateTaskProgress"
    TOOL_COMPLETE = "CompleteTask"
    TOOL_FAIL = "FailTask"
    TOOL_CREATE = "CreateBoardTask"

    ALL_TOOLS = frozenset(
        {
            TOOL_LIST,
            TOOL_CLAIM,
            TOOL_PROGRESS,
            TOOL_COMPLETE,
            TOOL_FAIL,
            TOOL_CREATE,
        }
    )

    def __init__(
        self,
        thread_id: str = "",
        auto_claim: bool = True,
        blocked_tools: frozenset[str] | set[str] | None = None,
    ):
        self.thread_id = thread_id
        self.auto_claim = auto_claim
        self._blocked_tools: frozenset[str] = frozenset(blocked_tools or ())

    # ------------------------------------------------------------------
    # Tool schemas
    # ------------------------------------------------------------------

    def _get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return OpenAI-format function schemas, filtered by blocked_tools."""
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": self.TOOL_LIST,
                    "description": ("List tasks on the board. Optionally filter by status or priority."),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "Status": {
                                "type": "string",
                                "description": "Filter by status (e.g. pending, running, completed, failed)",
                            },
                            "Priority": {
                                "type": "string",
                                "description": "Filter by priority (low, medium, high)",
                            },
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": self.TOOL_CLAIM,
                    "description": ("Claim a board task. Sets status to running, records thread_id and started_at."),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "TaskId": {
                                "type": "string",
                                "description": "The task ID to claim",
                            },
                        },
                        "required": ["TaskId"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": self.TOOL_PROGRESS,
                    "description": ("Update a task's progress percentage. Optionally append a note to the description."),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "TaskId": {
                                "type": "string",
                                "description": "The task ID to update",
                            },
                            "Progress": {
                                "type": "integer",
                                "description": "Progress percentage (0-100)",
                            },
                            "Note": {
                                "type": "string",
                                "description": "Optional note to append to the task description",
                            },
                        },
                        "required": ["TaskId", "Progress"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": self.TOOL_COMPLETE,
                    "description": ("Mark a board task as completed with a result summary. Sets progress to 100 and records completed_at."),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "TaskId": {
                                "type": "string",
                                "description": "The task ID to complete",
                            },
                            "Result": {
                                "type": "string",
                                "description": "Summary of what was accomplished",
                            },
                        },
                        "required": ["TaskId", "Result"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": self.TOOL_FAIL,
                    "description": ("Mark a board task as failed with a reason. Records completed_at."),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "TaskId": {
                                "type": "string",
                                "description": "The task ID to mark failed",
                            },
                            "Reason": {
                                "type": "string",
                                "description": "Why the task failed",
                            },
                        },
                        "required": ["TaskId", "Reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": self.TOOL_CREATE,
                    "description": ("Create a new task on the board. Source is automatically set to 'agent'."),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "Title": {
                                "type": "string",
                                "description": "Task title",
                            },
                            "Description": {
                                "type": "string",
                                "description": "Detailed description of the task",
                            },
                            "Priority": {
                                "type": "string",
                                "enum": ["low", "medium", "high"],
                                "description": "Task priority (default: medium)",
                            },
                        },
                        "required": ["Title"],
                    },
                },
            },
        ]
        return [s for s in schemas if s["function"]["name"] not in self._blocked_tools]

    # ------------------------------------------------------------------
    # Model call wrapping — inject tool schemas
    # ------------------------------------------------------------------

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        tools = list(request.tools or [])
        tools.extend(self._get_tool_schemas())
        return handler(request.override(tools=tools))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        tools = list(request.tools or [])
        tools.extend(self._get_tool_schemas())
        return await handler(request.override(tools=tools))

    # ------------------------------------------------------------------
    # Tool call wrapping — intercept owned tools
    # ------------------------------------------------------------------

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        tool_name = request.tool_call.get("name")
        if tool_name not in self.ALL_TOOLS:
            return handler(request)
        return self._handle_tool_call(request.tool_call)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        tool_name = request.tool_call.get("name")
        if tool_name not in self.ALL_TOOLS:
            return await handler(request)
        return await asyncio.to_thread(self._handle_tool_call, request.tool_call)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _handle_tool_call(self, tool_call: Mapping[str, Any] | ToolCall) -> ToolMessage:
        tool_name = tool_call.get("name")
        tool_id = tool_call.get("id", "")
        args = tool_call.get("args", {})

        if tool_name == self.TOOL_LIST:
            result = self._handle_list(args)
        elif tool_name == self.TOOL_CLAIM:
            result = self._handle_claim(args)
        elif tool_name == self.TOOL_PROGRESS:
            result = self._handle_progress(args)
        elif tool_name == self.TOOL_COMPLETE:
            result = self._handle_complete(args)
        elif tool_name == self.TOOL_FAIL:
            result = self._handle_fail(args)
        elif tool_name == self.TOOL_CREATE:
            result = self._handle_create(args)
        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        content = json.dumps(result, ensure_ascii=False, indent=2)
        return ToolMessage(content=content, tool_call_id=tool_id)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_list(self, args: dict) -> dict:
        """List board tasks with optional status/priority filter."""
        task_service = require_task_service()
        try:
            tasks = task_service.list_tasks()
        except Exception as e:
            logger.exception("[taskboard] list_tasks failed")
            return {"error": f"Failed to list tasks: {e}"}

        status_filter = args.get("Status")
        if status_filter:
            tasks = [t for t in tasks if t["status"] == status_filter]

        priority_filter = args.get("Priority")
        if priority_filter:
            tasks = [t for t in tasks if t["priority"] == priority_filter]

        return {"tasks": tasks, "total": len(tasks)}

    def _handle_claim(self, args: dict) -> dict:
        """Claim a task: set running + thread_id + started_at."""
        task_service = require_task_service()
        task_id = args.get("TaskId", "")
        now_ms = int(time.time() * 1000)
        updated = task_service.update_task(
            task_id,
            status="running",
            thread_id=self.thread_id,
            started_at=now_ms,
        )
        if updated is None:
            return {"error": f"Task not found: {task_id}"}
        return {"task": updated}

    def _handle_progress(self, args: dict) -> dict:
        """Update task progress and optionally append a note."""
        task_service = require_task_service()
        task_id = args.get("TaskId", "")
        progress = args.get("Progress", 0)

        # Build update kwargs
        update_kwargs: dict[str, Any] = {"progress": progress}

        note = args.get("Note")
        if note:
            current = task_service.get_task(task_id)
            if current is None:
                return {"error": f"Task not found: {task_id}"}
            existing = current.get("description", "")
            separator = "\n" if existing else ""
            update_kwargs["description"] = f"{existing}{separator}{note}"

        updated = task_service.update_task(task_id, **update_kwargs)
        if updated is None:
            return {"error": f"Task not found: {task_id}"}
        return {"task": updated}

    def _handle_complete(self, args: dict) -> dict:
        """Complete a task with result."""
        task_service = require_task_service()
        task_id = args.get("TaskId", "")
        result_text = args.get("Result", "")
        now_ms = int(time.time() * 1000)
        updated = task_service.update_task(
            task_id,
            status="completed",
            result=result_text,
            progress=100,
            completed_at=now_ms,
        )
        if updated is None:
            return {"error": f"Task not found: {task_id}"}
        return {"task": updated}

    def _handle_fail(self, args: dict) -> dict:
        """Fail a task with reason."""
        task_service = require_task_service()
        task_id = args.get("TaskId", "")
        reason = args.get("Reason", "")
        now_ms = int(time.time() * 1000)
        updated = task_service.update_task(
            task_id,
            status="failed",
            result=reason,
            completed_at=now_ms,
        )
        if updated is None:
            return {"error": f"Task not found: {task_id}"}
        return {"task": updated}

    # ------------------------------------------------------------------
    # Idle callback
    # ------------------------------------------------------------------

    async def on_idle(self) -> dict[str, Any] | None:
        """Called when agent enters IDLE state. Returns highest-priority pending task, or None."""
        task_service = require_task_service()
        return await asyncio.to_thread(task_service.get_highest_priority_pending_task)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_create(self, args: dict) -> dict:
        """Create a board task with source='agent'."""
        task_service = require_task_service()
        try:
            task = task_service.create_task(
                title=args.get("Title", "New task"),
                description=args.get("Description", ""),
                priority=args.get("Priority", "medium"),
                source="agent",
            )
        except Exception as e:
            logger.exception("[taskboard] create_task failed")
            return {"error": f"Failed to create task: {e}"}
        return {"task": task}
