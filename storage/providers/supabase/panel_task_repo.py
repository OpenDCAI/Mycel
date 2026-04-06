"""Supabase repository for panel task board records."""

from __future__ import annotations

import time
import uuid
from typing import Any

from storage.providers.supabase import _query as q

_REPO = "panel_task repo"
_TABLE = "panel_tasks"

TASK_STATUS_ALIASES = {"done": "completed"}


class SupabasePanelTaskRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _table(self) -> Any:
        return self._client.table(_TABLE)

    def _deserialize(self, row: dict[str, Any]) -> dict[str, Any]:
        row = dict(row)
        row["status"] = TASK_STATUS_ALIASES.get(row.get("status", ""), row.get("status", ""))
        if isinstance(row.get("tags"), str):
            import json

            try:
                row["tags"] = json.loads(row["tags"])
            except Exception:
                row["tags"] = []
        elif row.get("tags") is None:
            row["tags"] = []
        return row

    def list_all(self, owner_user_id: str | None = None) -> list[dict[str, Any]]:
        query = self._table().select("*")
        if owner_user_id is not None:
            query = query.eq("owner_user_id", owner_user_id)
        rows = q.rows(
            q.order(query, "created_at", desc=True, repo=_REPO, operation="list_all").execute(),
            _REPO,
            "list_all",
        )
        return [self._deserialize(r) for r in rows]

    def get(self, task_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            self._table().select("*").eq("id", task_id).execute(),
            _REPO,
            "get",
        )
        return self._deserialize(rows[0]) if rows else None

    def get_highest_priority_pending(self, owner_user_id: str | None = None) -> dict[str, Any] | None:
        query = self._table().select("*").eq("status", "pending")
        if owner_user_id is not None:
            query = query.eq("owner_user_id", owner_user_id)
        rows = q.rows(
            query.execute(),
            _REPO,
            "get_highest_priority_pending",
        )
        if not rows:
            return None
        priority_order = {"high": 0, "medium": 1, "low": 2}
        rows.sort(key=lambda r: (priority_order.get(r.get("priority", ""), 99), r.get("created_at", 0)))
        return self._deserialize(rows[0])

    def create(self, **fields: Any) -> dict[str, Any]:
        task_id = uuid.uuid4().hex
        now = int(time.time() * 1000)
        tags = fields.get("tags", [])
        self._table().insert(
            {
                "id": task_id,
                "title": fields.get("title", "新任务"),
                "description": fields.get("description", ""),
                "assignee_id": fields.get("assignee_id", ""),
                "status": "pending",
                "priority": fields.get("priority", "medium"),
                "progress": 0,
                "deadline": fields.get("deadline", ""),
                "created_at": now,
                "thread_id": fields.get("thread_id", ""),
                "source": fields.get("source", "manual"),
                "cron_job_id": fields.get("cron_job_id", ""),
                "result": fields.get("result", ""),
                "started_at": fields.get("started_at", 0),
                "completed_at": fields.get("completed_at", 0),
                "tags": tags,
                "owner_user_id": fields.get("owner_user_id", None),
            }
        ).execute()
        return self.get(task_id) or {}

    def update(self, task_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {
            "title",
            "description",
            "assignee_id",
            "status",
            "priority",
            "progress",
            "deadline",
            "thread_id",
            "source",
            "cron_job_id",
            "result",
            "started_at",
            "completed_at",
            "tags",
            "owner_user_id",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get(task_id)
        self._table().update(updates).eq("id", task_id).execute()
        return self.get(task_id)

    def delete(self, task_id: str) -> bool:
        rows = q.rows(
            self._table().delete().eq("id", task_id).execute(),
            _REPO,
            "delete",
        )
        return len(rows) > 0

    def bulk_delete(self, ids: list[str]) -> int:
        if not ids:
            return 0
        rows = q.rows(
            q.in_(self._table().delete(), "id", ids, _REPO, "bulk_delete").execute(),
            _REPO,
            "bulk_delete",
        )
        return len(rows)

    def bulk_update_status(self, ids: list[str], status: str) -> int:
        if not ids:
            return 0
        updates: dict[str, Any] = {"status": status}
        if status == "completed":
            updates["progress"] = 100
        elif status == "pending":
            updates["progress"] = 0
        rows = q.rows(
            q.in_(self._table().update(updates), "id", ids, _REPO, "bulk_update_status").execute(),
            _REPO,
            "bulk_update_status",
        )
        return len(rows)
