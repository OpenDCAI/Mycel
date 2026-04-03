"""Supabase repository for cron job records."""

from __future__ import annotations

import time
import uuid
from typing import Any

from storage.providers.supabase import _query as q

_REPO = "cron_job repo"
_TABLE = "cron_jobs"


class SupabaseCronJobRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _table(self) -> Any:
        return self._client.table(_TABLE)

    def _deserialize(self, row: dict[str, Any]) -> dict[str, Any]:
        row = dict(row)
        if isinstance(row.get("task_template"), str):
            import json
            try:
                row["task_template"] = json.loads(row["task_template"])
            except Exception:
                row["task_template"] = {}
        return row

    def list_all(self) -> list[dict[str, Any]]:
        rows = q.rows(
            q.order(self._table().select("*"), "created_at", desc=True, repo=_REPO, operation="list_all").execute(),
            _REPO, "list_all",
        )
        return [self._deserialize(r) for r in rows]

    def get(self, job_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            self._table().select("*").eq("id", job_id).execute(),
            _REPO, "get",
        )
        return self._deserialize(rows[0]) if rows else None

    def create(self, *, name: str, cron_expression: str, **fields: Any) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        now = int(time.time() * 1000)
        task_template = fields.get("task_template", {})
        if isinstance(task_template, str):
            import json
            try:
                task_template = json.loads(task_template)
            except Exception:
                task_template = {}
        self._table().insert({
            "id": job_id,
            "name": name,
            "description": fields.get("description", ""),
            "cron_expression": cron_expression,
            "task_template": task_template,
            "enabled": fields.get("enabled", True),
            "last_run_at": fields.get("last_run_at", 0),
            "next_run_at": fields.get("next_run_at", 0),
            "created_at": now,
        }).execute()
        return self.get(job_id) or {}

    def update(self, job_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {"name", "description", "cron_expression", "task_template", "enabled", "last_run_at", "next_run_at"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if "task_template" in updates and isinstance(updates["task_template"], str):
            import json
            try:
                updates["task_template"] = json.loads(updates["task_template"])
            except Exception:
                updates["task_template"] = {}
        if not updates:
            return self.get(job_id)
        self._table().update(updates).eq("id", job_id).execute()
        return self.get(job_id)

    def delete(self, job_id: str) -> bool:
        rows = q.rows(
            self._table().delete().eq("id", job_id).execute(),
            _REPO, "delete",
        )
        return len(rows) > 0
