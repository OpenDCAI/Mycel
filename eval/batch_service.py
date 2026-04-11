from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


class EvaluationBatchService:
    def __init__(self, *, batch_repo) -> None:
        self._batch_repo = batch_repo

    def create_batch(
        self,
        *,
        submitted_by_user_id: str,
        agent_user_id: str,
        scenario_ids: list[str],
        sandbox: str,
        max_concurrent: int,
    ) -> dict:
        now = datetime.now(UTC).isoformat()
        batch_id = f"eval-batch-{uuid4().hex[:12]}"
        batch = self._batch_repo.create_batch(
            {
                "batch_id": batch_id,
                "kind": "scenario_batch",
                "submitted_by_user_id": submitted_by_user_id,
                "agent_user_id": agent_user_id,
                "config_json": {
                    "scenario_ids": list(scenario_ids),
                    "sandbox": sandbox,
                    "max_concurrent": max_concurrent,
                },
                "status": "pending",
                "created_at": now,
                "updated_at": now,
                "summary_json": {
                    "total_runs": len(scenario_ids),
                    "running_runs": 0,
                    "completed_runs": 0,
                    "failed_runs": 0,
                },
            }
        )
        for scenario_id in scenario_ids:
            self._batch_repo.create_batch_run(
                {
                    "batch_run_id": f"eval-batch-run-{uuid4().hex[:12]}",
                    "batch_id": batch_id,
                    "item_key": scenario_id,
                    "scenario_id": scenario_id,
                    "status": "pending",
                    "thread_id": None,
                    "eval_run_id": None,
                    "started_at": None,
                    "finished_at": None,
                    "summary_json": {},
                }
            )
        return batch

    def list_batches(self, limit: int = 50) -> list[dict]:
        return self._batch_repo.list_batches(limit=limit)

    def get_batch_detail(self, batch_id: str) -> dict:
        batch = self._batch_repo.get_batch(batch_id)
        if batch is None:
            raise KeyError(f"Evaluation batch not found: {batch_id}")
        return {
            "batch": batch,
            "runs": self._batch_repo.list_batch_runs(batch_id),
        }

    def get_batch_run_for_eval_run(self, eval_run_id: str) -> dict | None:
        return self._batch_repo.get_batch_run_by_eval_run_id(eval_run_id)

    def refresh_batch_summary(self, batch_id: str) -> dict:
        batch_runs = self._batch_repo.list_batch_runs(batch_id)
        summary = {
            "total_runs": len(batch_runs),
            "running_runs": sum(1 for row in batch_runs if row.get("status") == "running"),
            "completed_runs": sum(1 for row in batch_runs if row.get("status") == "completed"),
            "failed_runs": sum(1 for row in batch_runs if row.get("status") in {"failed", "cancelled"}),
        }
        updated = self._batch_repo.update_batch(
            batch_id,
            summary_json=summary,
            updated_at=datetime.now(UTC).isoformat(),
        )
        if updated is None:
            raise KeyError(f"Evaluation batch not found: {batch_id}")
        return summary

    def link_batch_run_to_eval_run(
        self,
        batch_run_id: str,
        *,
        thread_id: str,
        eval_run_id: str,
        status: str,
    ) -> dict:
        updates = {
            "thread_id": thread_id,
            "eval_run_id": eval_run_id,
            "status": status,
        }
        if status in {"completed", "failed", "cancelled"}:
            updates["finished_at"] = datetime.now(UTC).isoformat()
        updated = self._batch_repo.update_batch_run(
            batch_run_id,
            **updates,
        )
        if updated is None:
            raise KeyError(f"Evaluation batch run not found: {batch_run_id}")
        self.refresh_batch_summary(str(updated["batch_id"]))
        return updated

    def mark_batch_run_running(self, batch_run_id: str, *, thread_id: str) -> dict:
        updated = self._batch_repo.update_batch_run(
            batch_run_id,
            thread_id=thread_id,
            status="running",
            started_at=datetime.now(UTC).isoformat(),
        )
        if updated is None:
            raise KeyError(f"Evaluation batch run not found: {batch_run_id}")
        self.refresh_batch_summary(str(updated["batch_id"]))
        return updated

    def record_eval_result(self, batch_id: str, result: Any) -> dict:
        batch_run = self._find_batch_run_for_scenario(batch_id, str(result.scenario_id))
        summary = {
            "total_tokens": int(result.system_metrics.total_tokens),
            "tool_call_count": int(result.system_metrics.tool_call_count),
        }
        updated = self._batch_repo.update_batch_run(
            batch_run["batch_run_id"],
            thread_id=result.trajectory.thread_id,
            eval_run_id=result.trajectory.id,
            status=result.trajectory.status,
            finished_at=datetime.now(UTC).isoformat(),
            summary_json=summary,
        )
        if updated is None:
            raise KeyError(f"Evaluation batch run not found: {batch_run['batch_run_id']}")
        self.refresh_batch_summary(batch_id)
        return updated

    def record_eval_error(self, batch_id: str, scenario_id: str, exc: BaseException) -> dict:
        batch_run = self._find_batch_run_for_scenario(batch_id, scenario_id)
        updated = self._batch_repo.update_batch_run(
            batch_run["batch_run_id"],
            status="failed",
            finished_at=datetime.now(UTC).isoformat(),
            summary_json={"error": str(exc)},
        )
        if updated is None:
            raise KeyError(f"Evaluation batch run not found: {batch_run['batch_run_id']}")
        self.refresh_batch_summary(batch_id)
        return updated

    def _find_batch_run_for_scenario(self, batch_id: str, scenario_id: str) -> dict:
        for batch_run in self._batch_repo.list_batch_runs(batch_id):
            if str(batch_run.get("scenario_id") or "") == scenario_id:
                return batch_run
        raise KeyError(f"Evaluation batch run not found for scenario {scenario_id} in batch {batch_id}")
