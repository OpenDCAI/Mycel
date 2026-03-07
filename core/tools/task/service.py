"""TaskService - Task management tools (migrated from TodoMiddleware).

Provides TaskCreate/TaskGet/TaskList/TaskUpdate as DEFERRED tools,
discoverable via tool_search rather than injected into every model call.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry
from core.todo.types import Task, TaskStatus

logger = logging.getLogger(__name__)

TASK_CREATE_SCHEMA = {
    "name": "TaskCreate",
    "description": (
        "Create a new task to track work progress. "
        "Tasks are created with status 'pending'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": "Brief task title in imperative form",
            },
            "description": {
                "type": "string",
                "description": "Detailed description of what needs to be done",
            },
            "active_form": {
                "type": "string",
                "description": "Present continuous form for spinner display",
            },
            "metadata": {
                "type": "object",
                "description": "Optional metadata to attach to the task",
            },
        },
        "required": ["subject", "description"],
    },
}

TASK_GET_SCHEMA = {
    "name": "TaskGet",
    "description": "Get full details of a task including description and dependencies.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The task ID to retrieve",
            },
        },
        "required": ["task_id"],
    },
}

TASK_LIST_SCHEMA = {
    "name": "TaskList",
    "description": (
        "List all tasks with summary info: id, subject, status, owner, blockedBy."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

TASK_UPDATE_SCHEMA = {
    "name": "TaskUpdate",
    "description": (
        "Update a task's status, dependencies, or other fields. "
        "Status flow: pending -> in_progress -> completed. "
        "Use status='deleted' to remove a task."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The task ID to update",
            },
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "completed", "deleted"],
                "description": "New status for the task",
            },
            "subject": {
                "type": "string",
                "description": "New subject for the task",
            },
            "description": {
                "type": "string",
                "description": "New description for the task",
            },
            "active_form": {
                "type": "string",
                "description": "New activeForm for the task",
            },
            "owner": {
                "type": "string",
                "description": "Assign task to an agent",
            },
            "add_blocks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Task IDs that this task blocks",
            },
            "add_blocked_by": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Task IDs that block this task",
            },
            "metadata": {
                "type": "object",
                "description": "Metadata keys to merge (set key to null to delete)",
            },
        },
        "required": ["task_id"],
    },
}


class TaskService:
    """Task management service providing DEFERRED tools.

    Migrated from TodoMiddleware. Uses in-memory storage per agent instance.
    """

    def __init__(self, registry: ToolRegistry, workspace_root: str | None = None):
        self._tasks: dict[str, Task] = {}
        self._counter = 0
        self._register(registry)
        logger.info("TaskService initialized")

    def _register(self, registry: ToolRegistry) -> None:
        for name, schema, handler in [
            ("TaskCreate", TASK_CREATE_SCHEMA, self._create),
            ("TaskGet", TASK_GET_SCHEMA, self._get),
            ("TaskList", TASK_LIST_SCHEMA, self._list),
            ("TaskUpdate", TASK_UPDATE_SCHEMA, self._update),
        ]:
            registry.register(
                ToolEntry(
                    name=name,
                    mode=ToolMode.DEFERRED,
                    schema=schema,
                    handler=handler,
                    source="TaskService",
                )
            )

    def _generate_id(self) -> str:
        self._counter += 1
        return str(self._counter)

    def _create(self, **args: Any) -> str:
        task_id = self._generate_id()
        task = Task(
            id=task_id,
            subject=args.get("subject", ""),
            description=args.get("description", ""),
            active_form=args.get("active_form"),
            metadata=args.get("metadata", {}),
        )
        self._tasks[task_id] = task
        return json.dumps(
            {"id": task_id, "status": "created", "task": task.to_summary()},
            ensure_ascii=False,
            indent=2,
        )

    def _get(self, **args: Any) -> str:
        task_id = args.get("task_id", "")
        if task_id not in self._tasks:
            return json.dumps({"error": f"Task not found: {task_id}"})
        return json.dumps(self._tasks[task_id].to_detail(), ensure_ascii=False, indent=2)

    def _list(self, **args: Any) -> str:
        tasks = []
        for task in self._tasks.values():
            summary = task.to_summary()
            summary["isBlocked"] = task.is_blocked(self._tasks)
            tasks.append(summary)

        return json.dumps(
            {
                "tasks": tasks,
                "total": len(tasks),
                "pending": sum(1 for t in self._tasks.values() if t.status == TaskStatus.PENDING),
                "in_progress": sum(1 for t in self._tasks.values() if t.status == TaskStatus.IN_PROGRESS),
                "completed": sum(1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED),
            },
            ensure_ascii=False,
            indent=2,
        )

    def _update(self, **args: Any) -> str:
        task_id = args.get("task_id", "")
        if task_id not in self._tasks:
            return json.dumps({"error": f"Task not found: {task_id}"})

        task = self._tasks[task_id]

        # Handle deletion
        status = args.get("status")
        if status == "deleted":
            for other_task in self._tasks.values():
                if task_id in other_task.blocks:
                    other_task.blocks.remove(task_id)
                if task_id in other_task.blocked_by:
                    other_task.blocked_by.remove(task_id)
            del self._tasks[task_id]
            return json.dumps({"status": "deleted", "id": task_id})

        # Update status
        if status:
            try:
                task.status = TaskStatus(status)
            except ValueError:
                valid = ", ".join(s.value for s in TaskStatus)
                return json.dumps({"error": f"Invalid status '{status}'. Valid: {valid}"})

        # Update fields
        if "subject" in args:
            task.subject = args["subject"]
        if "description" in args:
            task.description = args["description"]
        if "active_form" in args:
            task.active_form = args["active_form"]
        if "owner" in args:
            task.owner = args["owner"]

        # Add dependencies
        if "add_blocks" in args:
            for blocked_id in args["add_blocks"]:
                if blocked_id not in task.blocks:
                    task.blocks.append(blocked_id)
                if blocked_id in self._tasks and task_id not in self._tasks[blocked_id].blocked_by:
                    self._tasks[blocked_id].blocked_by.append(task_id)

        if "add_blocked_by" in args:
            for blocker_id in args["add_blocked_by"]:
                if blocker_id not in task.blocked_by:
                    task.blocked_by.append(blocker_id)
                if blocker_id in self._tasks and task_id not in self._tasks[blocker_id].blocks:
                    self._tasks[blocker_id].blocks.append(task_id)

        # Merge metadata
        if "metadata" in args:
            for key, value in args["metadata"].items():
                if value is None:
                    task.metadata.pop(key, None)
                else:
                    task.metadata[key] = value

        return json.dumps(
            {"status": "updated", "task": task.to_summary()},
            ensure_ascii=False,
            indent=2,
        )

    def get_tasks(self) -> dict[str, Task]:
        return self._tasks.copy()

    def get_active_task(self) -> Task | None:
        for task in self._tasks.values():
            if task.status == TaskStatus.IN_PROGRESS:
                return task
        return None
