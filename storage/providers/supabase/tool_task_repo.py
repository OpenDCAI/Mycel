"""Supabase repository for thread-scoped tool tasks."""

from __future__ import annotations

import json
from typing import Any

from core.tools.task.types import Task, TaskStatus
from storage.providers.supabase import _query as q

_REPO = "tool_task repo"
_TABLE = "tool_tasks"


class SupabaseToolTaskRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _table(self) -> Any:
        return self._client.table(_TABLE)

    def next_id(self, thread_id: str) -> str:
        rows = q.rows(
            self._table().select("task_id", count="exact").eq("thread_id", thread_id).execute(),
            _REPO,
            "next_id",
        )
        return str(len(rows) + 1)

    def get(self, thread_id: str, task_id: str) -> Task | None:
        rows = q.rows(
            self._table().select("*").eq("thread_id", thread_id).eq("task_id", task_id).execute(),
            _REPO,
            "get",
        )
        return self._row_to_task(rows[0]) if rows else None

    def list_all(self, thread_id: str) -> list[Task]:
        rows = q.rows(
            q.order(
                self._table().select("*").eq("thread_id", thread_id),
                "task_id",
                desc=False,
                repo=_REPO,
                operation="list_all",
            ).execute(),
            _REPO,
            "list_all",
        )
        return [self._row_to_task(r) for r in rows]

    def insert(self, thread_id: str, task: Task) -> None:
        self._table().insert(
            {
                "thread_id": thread_id,
                "task_id": task.id,
                "subject": task.subject,
                "description": task.description,
                "status": task.status.value,
                "active_form": task.active_form,
                "owner": task.owner,
                "blocks": task.blocks,
                "blocked_by": task.blocked_by,
                "metadata": task.metadata,
            }
        ).execute()

    def update(self, thread_id: str, task: Task) -> None:
        self._table().update(
            {
                "subject": task.subject,
                "description": task.description,
                "status": task.status.value,
                "active_form": task.active_form,
                "owner": task.owner,
                "blocks": task.blocks,
                "blocked_by": task.blocked_by,
                "metadata": task.metadata,
            }
        ).eq("thread_id", thread_id).eq("task_id", task.id).execute()

    def delete(self, thread_id: str, task_id: str) -> None:
        self._table().delete().eq("thread_id", thread_id).eq("task_id", task_id).execute()

    @staticmethod
    def _row_to_task(row: dict[str, Any]) -> Task:
        blocks = row.get("blocks", [])
        blocked_by = row.get("blocked_by", [])
        metadata = row.get("metadata", {})
        if isinstance(blocks, str):
            blocks = json.loads(blocks)
        if isinstance(blocked_by, str):
            blocked_by = json.loads(blocked_by)
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return Task(
            id=row["task_id"],
            subject=row["subject"],
            description=row["description"],
            status=TaskStatus(row["status"]),
            active_form=row.get("active_form"),
            owner=row.get("owner"),
            blocks=blocks,
            blocked_by=blocked_by,
            metadata=metadata,
        )
