"""TaskService - SQLite-backed task management tools.

Provides TaskCreate/TaskGet/TaskList/TaskUpdate as DEFERRED tools.
Tasks are partitioned by thread_id so all agents in the same thread share
the same task list. Thread ID is read from sandbox.thread_context at runtime.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry
from core.tools.task.types import Task, TaskStatus
from storage.providers.sqlite.tool_task_repo import SQLiteToolTaskRepo

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path.home() / ".leon" / "tasks.db"

TASK_CREATE_SCHEMA = {
    "name": "TaskCreate",
    "description": (
        "Create a task to track multi-step work. "
        "Use for complex tasks with 3+ steps or when managing multiple parallel workstreams. "
        "Status starts as 'pending'."
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
    "description": ("List all tasks with summary info: id, subject, status, owner, blockedBy."),
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

    Tasks are stored in SQLite and partitioned by thread_id so all agents
    in the same thread/team share the same task list.

    thread_id is resolved at call time from sandbox.thread_context;
    falls back to a fixed thread_id if provided at construction (for tests).
    """

    def __init__(
        self,
        registry: ToolRegistry,
        workspace_root: str | None = None,
        db_path: Path | None = None,
        thread_id: str | None = None,
    ):
        self._repo = SQLiteToolTaskRepo(db_path or DEFAULT_DB_PATH)
        self._default_thread_id = thread_id  # override for tests / single-agent TUI
        self._register(registry)
        logger.info("TaskService initialized (db=%s)", db_path or DEFAULT_DB_PATH)

    def _get_thread_id(self) -> str:
        if self._default_thread_id:
            return self._default_thread_id
        from sandbox.thread_context import get_current_thread_id

        tid = get_current_thread_id()
        return tid or "default"

    def _register(self, registry: ToolRegistry) -> None:
        _READ_ONLY = {"TaskGet", "TaskList"}
        for name, schema, handler in [
            ("TaskCreate", TASK_CREATE_SCHEMA, self._create),
            ("TaskGet", TASK_GET_SCHEMA, self._get),
            ("TaskList", TASK_LIST_SCHEMA, self._list),
            ("TaskUpdate", TASK_UPDATE_SCHEMA, self._update),
        ]:
            ro = name in _READ_ONLY
            registry.register(
                ToolEntry(
                    name=name,
                    mode=ToolMode.DEFERRED,
                    schema=schema,
                    handler=handler,
                    source="TaskService",
                    is_concurrency_safe=ro,
                    is_read_only=ro,
                )
            )

    # ── tool handlers ─────────────────────────────────────────────────────────

    def _create(self, **args: Any) -> str:
        thread_id = self._get_thread_id()
        task_id = self._repo.next_id(thread_id)
        task = Task(
            id=task_id,
            subject=args.get("subject", ""),
            description=args.get("description", ""),
            active_form=args.get("active_form"),
            metadata=args.get("metadata", {}),
        )
        self._repo.insert(thread_id, task)
        return json.dumps(
            {"id": task_id, "status": "created", "task": task.to_summary()},
            ensure_ascii=False,
            indent=2,
        )

    def _get(self, **args: Any) -> str:
        thread_id = self._get_thread_id()
        task_id = args.get("task_id", "")
        task = self._repo.get(thread_id, task_id)
        if task is None:
            return json.dumps({"error": f"Task not found: {task_id}"})
        return json.dumps(task.to_detail(), ensure_ascii=False, indent=2)

    def _list(self, **args: Any) -> str:
        thread_id = self._get_thread_id()
        tasks = self._repo.list_all(thread_id)
        tasks_by_id = {t.id: t for t in tasks}
        summaries = []
        for task in tasks:
            summary = task.to_summary()
            summary["isBlocked"] = task.is_blocked(tasks_by_id)
            summaries.append(summary)

        return json.dumps(
            {
                "tasks": summaries,
                "total": len(tasks),
                "pending": sum(1 for t in tasks if t.status == TaskStatus.PENDING),
                "in_progress": sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS),
                "completed": sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
            },
            ensure_ascii=False,
            indent=2,
        )

    def _update(self, **args: Any) -> str:
        thread_id = self._get_thread_id()
        task_id = args.get("task_id", "")
        task = self._repo.get(thread_id, task_id)
        if task is None:
            return json.dumps({"error": f"Task not found: {task_id}"})

        status = args.get("status")

        # Handle deletion — clean up dependency refs
        if status == "deleted":
            all_tasks = self._repo.list_all(thread_id)
            for other in all_tasks:
                changed = False
                if task_id in other.blocks:
                    other.blocks.remove(task_id)
                    changed = True
                if task_id in other.blocked_by:
                    other.blocked_by.remove(task_id)
                    changed = True
                if changed:
                    self._repo.update(thread_id, other)
            self._repo.delete(thread_id, task_id)
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

        # Add dependency edges (bidirectional)
        if "add_blocks" in args:
            for blocked_id in args["add_blocks"]:
                if blocked_id not in task.blocks:
                    task.blocks.append(blocked_id)
                other = self._repo.get(thread_id, blocked_id)
                if other and task_id not in other.blocked_by:
                    other.blocked_by.append(task_id)
                    self._repo.update(thread_id, other)

        if "add_blocked_by" in args:
            for blocker_id in args["add_blocked_by"]:
                if blocker_id not in task.blocked_by:
                    task.blocked_by.append(blocker_id)
                other = self._repo.get(thread_id, blocker_id)
                if other and task_id not in other.blocks:
                    other.blocks.append(task_id)
                    self._repo.update(thread_id, other)

        # Merge metadata
        if "metadata" in args:
            for key, value in args["metadata"].items():
                if value is None:
                    task.metadata.pop(key, None)
                else:
                    task.metadata[key] = value

        self._repo.update(thread_id, task)
        return json.dumps(
            {"status": "updated", "task": task.to_summary()},
            ensure_ascii=False,
            indent=2,
        )

    # ── compatibility helpers (used by agent.py runtime introspection) ────────

    def get_tasks(self) -> dict[str, Task]:
        thread_id = self._get_thread_id()
        return {t.id: t for t in self._repo.list_all(thread_id)}

    def get_active_task(self) -> Task | None:
        thread_id = self._get_thread_id()
        for task in self._repo.list_all(thread_id):
            if task.status == TaskStatus.IN_PROGRESS:
                return task
        return None
