"""Supabase repository for agent schedule records."""

from __future__ import annotations

import uuid
from typing import Any

from storage.providers.supabase import _query as q

_REPO = "schedule repo"
_SCHEMA = "agent"
_SCHEDULES_TABLE = "schedules"
_RUNS_TABLE = "schedule_runs"


class SupabaseScheduleRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _schedules(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, _SCHEDULES_TABLE, _REPO)

    def _runs(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, _RUNS_TABLE, _REPO)

    def list_by_owner(self, owner_user_id: str) -> list[dict[str, Any]]:
        return q.rows(
            q.order(
                self._schedules().select("*").eq("owner_user_id", owner_user_id),
                "created_at",
                desc=True,
                repo=_REPO,
                operation="list_by_owner",
            ).execute(),
            _REPO,
            "list_by_owner",
        )

    def get(self, schedule_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            self._schedules().select("*").eq("id", schedule_id).execute(),
            _REPO,
            "get",
        )
        return rows[0] if rows else None

    def create(
        self,
        *,
        owner_user_id: str,
        agent_user_id: str,
        cron_expression: str,
        instruction_template: str,
        target_thread_id: str | None = None,
        create_thread_on_run: bool = False,
        enabled: bool = True,
        timezone: str = "UTC",
        next_run_at: str | None = None,
    ) -> dict[str, Any]:
        schedule_id = uuid.uuid4().hex
        payload = {
            "id": schedule_id,
            "owner_user_id": owner_user_id,
            "agent_user_id": agent_user_id,
            "target_thread_id": target_thread_id,
            "create_thread_on_run": create_thread_on_run,
            "cron_expression": cron_expression,
            "enabled": enabled,
            "instruction_template": instruction_template,
            "timezone": timezone,
            "next_run_at": next_run_at,
        }
        rows = q.rows(self._schedules().insert(payload).execute(), _REPO, "create")
        return rows[0] if rows else self.get(schedule_id) or {}

    def update(self, schedule_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {
            "agent_user_id",
            "target_thread_id",
            "create_thread_on_run",
            "cron_expression",
            "enabled",
            "instruction_template",
            "timezone",
            "last_run_at",
            "next_run_at",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return self.get(schedule_id)
        rows = q.rows(
            self._schedules().update(updates).eq("id", schedule_id).execute(),
            _REPO,
            "update",
        )
        return rows[0] if rows else None

    def delete(self, schedule_id: str) -> bool:
        rows = q.rows(
            self._schedules().delete().eq("id", schedule_id).execute(),
            _REPO,
            "delete",
        )
        return len(rows) > 0

    def create_run(
        self,
        *,
        schedule_id: str,
        owner_user_id: str,
        agent_user_id: str,
        triggered_by: str,
        thread_id: str | None = None,
        scheduled_for: str | None = None,
        input_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run_id = uuid.uuid4().hex
        payload = {
            "id": run_id,
            "schedule_id": schedule_id,
            "owner_user_id": owner_user_id,
            "agent_user_id": agent_user_id,
            "thread_id": thread_id,
            "triggered_by": triggered_by,
            "scheduled_for": scheduled_for,
            "input_json": input_json or {},
        }
        rows = q.rows(self._runs().insert(payload).execute(), _REPO, "create_run")
        return rows[0] if rows else self.get_run(run_id) or {}

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            self._runs().select("*").eq("id", run_id).execute(),
            _REPO,
            "get_run",
        )
        return rows[0] if rows else None

    def list_runs(self, schedule_id: str) -> list[dict[str, Any]]:
        return q.rows(
            q.order(
                self._runs().select("*").eq("schedule_id", schedule_id),
                "created_at",
                desc=True,
                repo=_REPO,
                operation="list_runs",
            ).execute(),
            _REPO,
            "list_runs",
        )

    def update_run(self, run_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {"thread_id", "status", "started_at", "completed_at", "output_json", "error"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return self.get_run(run_id)
        rows = q.rows(
            self._runs().update(updates).eq("id", run_id).execute(),
            _REPO,
            "update_run",
        )
        return rows[0] if rows else None

    def delete_run(self, run_id: str) -> bool:
        rows = q.rows(
            self._runs().delete().eq("id", run_id).execute(),
            _REPO,
            "delete_run",
        )
        return len(rows) > 0
