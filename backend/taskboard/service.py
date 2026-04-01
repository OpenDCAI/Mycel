"""TaskBoardService — registers board management tools into ToolRegistry.

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
from typing import Any

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry

# Lazy import: backend is only available when running as web service
try:
    from backend.web.services import task_service
except ImportError:
    task_service = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class TaskBoardService:
    """Registers board management tools into ToolRegistry.

    Tools go through ToolRegistry like all other tools — schema injection,
    blocking, and dispatch are handled uniformly by ToolRunner.
    """

    TOOL_LIST = "ListBoardTasks"
    TOOL_CLAIM = "ClaimTask"
    TOOL_PROGRESS = "UpdateTaskProgress"
    TOOL_COMPLETE = "CompleteTask"
    TOOL_FAIL = "FailTask"
    TOOL_CREATE = "CreateBoardTask"

    def __init__(self, registry: ToolRegistry, auto_claim: bool = True):
        self.auto_claim = auto_claim
        self._register(registry)

    def _register(self, registry: ToolRegistry) -> None:
        tools = [
            ToolEntry(
                name=self.TOOL_LIST,
                mode=ToolMode.INLINE,
                schema={
                    "name": self.TOOL_LIST,
                    "description": "List tasks on the board. Optionally filter by status or priority.",
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
                handler=self._list_tasks,
                source="TaskBoardService",
            ),
            ToolEntry(
                name=self.TOOL_CLAIM,
                mode=ToolMode.INLINE,
                schema={
                    "name": self.TOOL_CLAIM,
                    "description": "Claim a board task. Sets status to running, records thread_id and started_at.",
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
                handler=self._claim_task,
                source="TaskBoardService",
            ),
            ToolEntry(
                name=self.TOOL_PROGRESS,
                mode=ToolMode.INLINE,
                schema={
                    "name": self.TOOL_PROGRESS,
                    "description": "Update a task's progress percentage. Optionally append a note to the description.",
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
                handler=self._update_progress,
                source="TaskBoardService",
            ),
            ToolEntry(
                name=self.TOOL_COMPLETE,
                mode=ToolMode.INLINE,
                schema={
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
                handler=self._complete_task,
                source="TaskBoardService",
            ),
            ToolEntry(
                name=self.TOOL_FAIL,
                mode=ToolMode.INLINE,
                schema={
                    "name": self.TOOL_FAIL,
                    "description": "Mark a board task as failed with a reason. Records completed_at.",
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
                handler=self._fail_task,
                source="TaskBoardService",
            ),
            ToolEntry(
                name=self.TOOL_CREATE,
                mode=ToolMode.INLINE,
                schema={
                    "name": self.TOOL_CREATE,
                    "description": "Create a new task on the board. Source is automatically set to 'agent'.",
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
                handler=self._create_task,
                source="TaskBoardService",
            ),
        ]
        for entry in tools:
            registry.register(entry)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_thread_id(self) -> str:
        try:
            from sandbox.thread_context import get_current_thread_id

            return get_current_thread_id() or ""
        except ImportError:
            return ""

    # ------------------------------------------------------------------
    # Handlers (async — ToolRunner awaits coroutines)
    # ------------------------------------------------------------------

    async def _list_tasks(self, Status: str = "", Priority: str = "") -> str:
        try:
            tasks = await asyncio.to_thread(task_service.list_tasks)
        except Exception as e:
            logger.exception("[taskboard] list_tasks failed")
            return json.dumps({"error": f"Failed to list tasks: {e}"})

        if Status:
            tasks = [t for t in tasks if t["status"] == Status]
        if Priority:
            tasks = [t for t in tasks if t["priority"] == Priority]

        return json.dumps({"tasks": tasks, "total": len(tasks)}, ensure_ascii=False)

    async def _claim_task(self, TaskId: str) -> str:
        thread_id = self._get_thread_id()
        now_ms = int(time.time() * 1000)
        try:
            updated = await asyncio.to_thread(
                task_service.update_task,
                TaskId,
                status="running",
                thread_id=thread_id,
                started_at=now_ms,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

        if updated is None:
            return json.dumps({"error": f"Task not found: {TaskId}"})
        return json.dumps({"task": updated}, ensure_ascii=False)

    async def _update_progress(self, TaskId: str, Progress: int, Note: str = "") -> str:
        update_kwargs: dict[str, Any] = {"progress": Progress}

        if Note:
            try:
                current = await asyncio.to_thread(task_service.get_task, TaskId)
            except Exception as e:
                return json.dumps({"error": str(e)})
            if current is None:
                return json.dumps({"error": f"Task not found: {TaskId}"})
            existing = current.get("description", "")
            separator = "\n" if existing else ""
            update_kwargs["description"] = f"{existing}{separator}{Note}"

        try:
            updated = await asyncio.to_thread(task_service.update_task, TaskId, **update_kwargs)
        except Exception as e:
            return json.dumps({"error": str(e)})

        if updated is None:
            return json.dumps({"error": f"Task not found: {TaskId}"})
        return json.dumps({"task": updated}, ensure_ascii=False)

    async def _complete_task(self, TaskId: str, Result: str) -> str:
        now_ms = int(time.time() * 1000)
        try:
            updated = await asyncio.to_thread(
                task_service.update_task,
                TaskId,
                status="completed",
                result=Result,
                progress=100,
                completed_at=now_ms,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

        if updated is None:
            return json.dumps({"error": f"Task not found: {TaskId}"})
        return json.dumps({"task": updated}, ensure_ascii=False)

    async def _fail_task(self, TaskId: str, Reason: str) -> str:
        now_ms = int(time.time() * 1000)
        try:
            updated = await asyncio.to_thread(
                task_service.update_task,
                TaskId,
                status="failed",
                result=Reason,
                completed_at=now_ms,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

        if updated is None:
            return json.dumps({"error": f"Task not found: {TaskId}"})
        return json.dumps({"task": updated}, ensure_ascii=False)

    async def _create_task(self, Title: str, Description: str = "", Priority: str = "medium") -> str:
        try:
            task = await asyncio.to_thread(
                task_service.create_task,
                title=Title,
                description=Description,
                priority=Priority,
                source="agent",
            )
        except Exception as e:
            logger.exception("[taskboard] create_task failed")
            return json.dumps({"error": f"Failed to create task: {e}"})
        return json.dumps({"task": task}, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Idle callback
    # ------------------------------------------------------------------

    async def on_idle(self) -> dict[str, Any] | None:
        """Called when agent enters IDLE state. Returns highest-priority pending task, or None."""
        return await asyncio.to_thread(task_service.get_highest_priority_pending_task)
