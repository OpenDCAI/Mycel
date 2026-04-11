from __future__ import annotations

from typing import Any

from storage.providers.supabase import _query as q

_REPO = "evaluation_batch repo"
_BATCH_TABLE = "evaluation_batches"
_BATCH_RUN_TABLE = "evaluation_batch_runs"


class SupabaseEvaluationBatchRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def ensure_schema(self) -> None:
        return None

    def create_batch(self, batch: dict[str, Any]) -> dict[str, Any]:
        rows = q.rows(
            self._client.table(_BATCH_TABLE).insert(batch).execute(),
            _REPO,
            "create_batch",
        )
        if not rows:
            raise RuntimeError("Supabase evaluation batch repo expected inserted row for create_batch.")
        return self._map_batch(rows[0])

    def get_batch(self, batch_id: str) -> dict | None:
        rows = q.rows(
            self._client.table(_BATCH_TABLE).select("*").eq("batch_id", batch_id).execute(),
            _REPO,
            "get_batch",
        )
        if not rows:
            return None
        return self._map_batch(rows[0])

    def list_batches(self, limit: int = 50) -> list[dict[str, Any]]:
        query = self._client.table(_BATCH_TABLE).select("*")
        query = q.order(query, "created_at", desc=True, repo=_REPO, operation="list_batches")
        query = q.limit(query, limit, _REPO, "list_batches")
        return [self._map_batch(row) for row in q.rows(query.execute(), _REPO, "list_batches")]

    def update_batch(self, batch_id: str, **fields: Any) -> dict[str, Any] | None:
        updates = {key: value for key, value in fields.items() if value is not None}
        if not updates:
            return self.get_batch(batch_id)
        rows = q.rows(
            self._client.table(_BATCH_TABLE).update(updates).eq("batch_id", batch_id).execute(),
            _REPO,
            "update_batch",
        )
        if not rows:
            return None
        return self._map_batch(rows[0])

    def create_batch_run(self, batch_run: dict[str, Any]) -> dict[str, Any]:
        rows = q.rows(
            self._client.table(_BATCH_RUN_TABLE).insert(batch_run).execute(),
            _REPO,
            "create_batch_run",
        )
        if not rows:
            raise RuntimeError("Supabase evaluation batch repo expected inserted row for create_batch_run.")
        return self._map_batch_run(rows[0])

    def list_batch_runs(self, batch_id: str) -> list[dict[str, Any]]:
        query = self._client.table(_BATCH_RUN_TABLE).select("*").eq("batch_id", batch_id)
        query = q.order(query, "item_key", desc=False, repo=_REPO, operation="list_batch_runs")
        return [self._map_batch_run(row) for row in q.rows(query.execute(), _REPO, "list_batch_runs")]

    def update_batch_run(self, batch_run_id: str, **fields: Any) -> dict[str, Any] | None:
        updates = {key: value for key, value in fields.items() if value is not None}
        if not updates:
            rows = q.rows(
                self._client.table(_BATCH_RUN_TABLE).select("*").eq("batch_run_id", batch_run_id).execute(),
                _REPO,
                "update_batch_run get",
            )
            return self._map_batch_run(rows[0]) if rows else None
        rows = q.rows(
            self._client.table(_BATCH_RUN_TABLE).update(updates).eq("batch_run_id", batch_run_id).execute(),
            _REPO,
            "update_batch_run",
        )
        if not rows:
            return None
        return self._map_batch_run(rows[0])

    def _map_batch(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "batch_id": str(row.get("batch_id") or ""),
            "kind": str(row.get("kind") or ""),
            "submitted_by_user_id": str(row.get("submitted_by_user_id") or ""),
            "agent_user_id": str(row.get("agent_user_id") or ""),
            "config_json": row.get("config_json") or {},
            "status": str(row.get("status") or ""),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "summary_json": row.get("summary_json") or {},
        }

    def _map_batch_run(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "batch_run_id": str(row.get("batch_run_id") or ""),
            "batch_id": str(row.get("batch_id") or ""),
            "item_key": str(row.get("item_key") or ""),
            "scenario_id": str(row.get("scenario_id") or ""),
            "status": str(row.get("status") or ""),
            "thread_id": row.get("thread_id"),
            "eval_run_id": row.get("eval_run_id"),
            "started_at": row.get("started_at"),
            "finished_at": row.get("finished_at"),
            "summary_json": row.get("summary_json") or {},
        }
