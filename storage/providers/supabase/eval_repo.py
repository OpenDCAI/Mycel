"""Supabase repository for eval trajectory persistence operations."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from eval.models import RunTrajectory
from storage.providers.supabase import _query as q

_REPO = "eval repo"


class SupabaseEvalRepo:
    """Minimal eval repository backed by a Supabase client."""

    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def ensure_schema(self) -> None:
        """Supabase schema is managed via migrations, not runtime DDL."""
        return None

    def save_trajectory(self, trajectory: RunTrajectory, trajectory_json: str) -> str:
        run_id = trajectory.id
        run_rows = q.rows(
            self._t("eval_runs").insert({
                "id": run_id,
                "thread_id": trajectory.thread_id,
                "started_at": trajectory.started_at,
                "finished_at": trajectory.finished_at,
                "user_message": trajectory.user_message,
                "final_response": trajectory.final_response,
                "status": trajectory.status,
                "run_tree_json": trajectory.run_tree_json,
                "trajectory_json": trajectory_json,
            }).execute(),
            _REPO, "save_trajectory eval_runs",
        )
        if not run_rows:
            raise RuntimeError(
                "Supabase eval repo expected inserted row for save_trajectory eval_runs. "
                "Check table permissions."
            )
        if trajectory.llm_calls:
            llm_rows = [
                {
                    "id": str(uuid4()),
                    "run_id": run_id,
                    "parent_run_id": call.parent_run_id,
                    "duration_ms": call.duration_ms,
                    "input_tokens": call.input_tokens,
                    "output_tokens": call.output_tokens,
                    "total_tokens": call.total_tokens,
                    "cost_usd": call.cost_usd,
                    "model_name": call.model_name,
                }
                for call in trajectory.llm_calls
            ]
            q.rows(
                self._t("eval_llm_calls").insert(llm_rows).execute(),
                _REPO, "save_trajectory eval_llm_calls",
            )
        if trajectory.tool_calls:
            tool_rows = [
                {
                    "id": str(uuid4()),
                    "run_id": run_id,
                    "parent_run_id": call.parent_run_id,
                    "tool_name": call.tool_name,
                    "tool_call_id": call.tool_call_id,
                    "duration_ms": call.duration_ms,
                    "success": call.success,
                    "error": call.error,
                    "args_summary": call.args_summary,
                    "result_summary": call.result_summary,
                }
                for call in trajectory.tool_calls
            ]
            q.rows(
                self._t("eval_tool_calls").insert(tool_rows).execute(),
                _REPO, "save_trajectory eval_tool_calls",
            )
        return run_id

    def save_metrics(self, run_id: str, tier: str, timestamp: str, metrics_json: str) -> None:
        rows = q.rows(
            self._t("eval_metrics").insert({
                "id": str(uuid4()),
                "run_id": run_id,
                "tier": tier,
                "timestamp": timestamp,
                "metrics_json": metrics_json,
            }).execute(),
            _REPO, "save_metrics",
        )
        if not rows:
            raise RuntimeError(
                "Supabase eval repo expected inserted row for save_metrics. "
                "Check table permissions."
            )

    def get_trajectory_json(self, run_id: str) -> str | None:
        query = q.limit(
            self._t("eval_runs").select("trajectory_json").eq("id", run_id),
            1, _REPO, "get_trajectory_json",
        )
        rows = q.rows(query.execute(), _REPO, "get_trajectory_json")
        if not rows:
            return None
        val = rows[0].get("trajectory_json")
        if val is None:
            raise RuntimeError(
                "Supabase eval repo expected non-null trajectory_json in get_trajectory_json. "
                "Check eval_runs table schema."
            )
        return str(val)

    def list_runs(self, thread_id: str | None = None, limit: int = 50) -> list[dict]:
        query = self._t("eval_runs").select("id,thread_id,started_at,finished_at,status,user_message")
        if thread_id:
            query = query.eq("thread_id", thread_id)
        # @@@eval-list-order - newest started_at first, matching SQLite path.
        query = q.limit(q.order(query, "started_at", desc=True, repo=_REPO, operation="list_runs"), limit, _REPO, "list_runs")
        return [
            {
                "id": str(row.get("id") or ""),
                "thread_id": str(row.get("thread_id") or ""),
                "started_at": row.get("started_at"),
                "finished_at": row.get("finished_at"),
                "status": str(row.get("status") or ""),
                "user_message": str(row.get("user_message") or ""),
            }
            for row in q.rows(query.execute(), _REPO, "list_runs")
        ]

    def get_metrics(self, run_id: str, tier: str | None = None) -> list[dict]:
        query = self._t("eval_metrics").select("id,tier,timestamp,metrics_json").eq("run_id", run_id)
        if tier:
            query = query.eq("tier", tier)
        return [
            {
                "id": str(row.get("id") or ""),
                "tier": str(row.get("tier") or ""),
                "timestamp": row.get("timestamp"),
                "metrics_json": row.get("metrics_json"),
            }
            for row in q.rows(query.execute(), _REPO, "get_metrics")
        ]

    def _t(self, table_name: str) -> Any:
        return self._client.table(table_name)
