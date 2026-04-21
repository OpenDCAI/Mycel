from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from eval.models import EvalScenario


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
        scenario_refs: list[EvalScenario] | None = None,
    ) -> dict:
        now = datetime.now(UTC).isoformat()
        batch_id = f"eval-batch-{uuid4().hex[:12]}"
        scenario_refs = scenario_refs or []
        kind = "benchmark_batch" if any(scenario.benchmark for scenario in scenario_refs) else "scenario_batch"
        batch = self._batch_repo.create_batch(
            {
                "batch_id": batch_id,
                "kind": kind,
                "submitted_by_user_id": submitted_by_user_id,
                "agent_user_id": agent_user_id,
                "config_json": {
                    "scenario_ids": list(scenario_ids),
                    "sandbox": sandbox,
                    "max_concurrent": max_concurrent,
                    "scenario_refs": [self._serialize_scenario_ref(scenario) for scenario in scenario_refs],
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

    def list_batch_runs_for_thread(self, thread_id: str) -> list[dict]:
        return self._batch_repo.list_batch_runs_by_thread_id(thread_id)

    def update_batch_status(self, batch_id: str, status: str) -> dict:
        updated = self._batch_repo.update_batch(
            batch_id,
            status=status,
            updated_at=datetime.now(UTC).isoformat(),
        )
        if updated is None:
            raise KeyError(f"Evaluation batch not found: {batch_id}")
        return updated

    def refresh_batch_summary(self, batch_id: str) -> dict:
        batch_runs = self._batch_repo.list_batch_runs(batch_id)
        summary = {
            "total_runs": len(batch_runs),
            "running_runs": sum(1 for row in batch_runs if row.get("status") == "running"),
            "completed_runs": sum(1 for row in batch_runs if row.get("status") == "completed"),
            "failed_runs": sum(1 for row in batch_runs if row.get("status") in {"failed", "cancelled"}),
        }
        scored_runs = 0
        passed_runs = 0
        failed_judges = 0
        total_tokens = 0
        total_artifacts = 0
        score_totals: dict[str, float] = {}
        score_counts: dict[str, int] = {}
        benchmark_families: set[str] = set()
        benchmark_splits: set[str] = set()
        for row in batch_runs:
            row_summary = row.get("summary_json") or {}
            benchmark_family = str(row_summary.get("benchmark_family") or "").strip()
            benchmark_split = str(row_summary.get("benchmark_split") or "").strip()
            if benchmark_family:
                benchmark_families.add(benchmark_family)
            if benchmark_split:
                benchmark_splits.add(benchmark_split)
            total_tokens += int(row_summary.get("total_tokens") or 0)
            total_artifacts += int(row_summary.get("artifact_count") or 0)
            verdict = str(row_summary.get("judge_verdict") or "").strip().lower()
            if verdict:
                scored_runs += 1
                if verdict == "passed":
                    passed_runs += 1
                elif verdict in {"failed", "error"}:
                    failed_judges += 1
            for key, value in dict(row_summary.get("scores") or {}).items():
                score_totals[str(key)] = score_totals.get(str(key), 0.0) + float(value)
                score_counts[str(key)] = score_counts.get(str(key), 0) + 1
        summary["judge_passed_runs"] = passed_runs
        summary["judge_failed_runs"] = failed_judges
        summary["pass_rate"] = passed_runs / scored_runs if scored_runs else 0.0
        summary["avg_total_tokens"] = total_tokens / max(1, summary["completed_runs"])
        summary["artifact_count_total"] = total_artifacts
        summary["avg_scores"] = {
            key: score_totals[key] / score_counts[key]
            for key in sorted(score_totals)
            if score_counts.get(key)
        }
        summary["benchmark_families"] = sorted(benchmark_families)
        summary["benchmark_splits"] = sorted(benchmark_splits)
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
        finished_at = datetime.now(UTC).isoformat() if status in {"completed", "failed", "cancelled"} else None
        updated = self._batch_repo.update_batch_run(
            batch_run_id,
            thread_id=thread_id,
            eval_run_id=eval_run_id,
            status=status,
            finished_at=finished_at,
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

    def mark_batch_run_running_for_scenario(self, batch_id: str, scenario_id: str) -> dict:
        batch_run = self._find_batch_run_for_scenario(batch_id, scenario_id)
        updated = self._batch_repo.update_batch_run(
            batch_run["batch_run_id"],
            status="running",
            started_at=datetime.now(UTC).isoformat(),
        )
        if updated is None:
            raise KeyError(f"Evaluation batch run not found: {batch_run['batch_run_id']}")
        self.refresh_batch_summary(batch_id)
        return updated

    def record_eval_result(self, batch_id: str, result: Any) -> dict:
        batch_run = self._find_batch_run_for_scenario(batch_id, str(result.scenario_id))
        summary = {
            "total_tokens": int(result.system_metrics.total_tokens),
            "tool_call_count": int(result.system_metrics.tool_call_count),
            "artifact_count": len(result.artifacts),
            "benchmark_family": result.benchmark.family if result.benchmark else "",
            "benchmark_name": result.benchmark.name if result.benchmark else "",
            "benchmark_split": result.benchmark.split if result.benchmark else "",
            "instance_id": result.benchmark.instance_id if result.benchmark else "",
            "judge_type": result.judge_result.judge_type if result.judge_result else "",
            "judge_status": result.judge_result.status if result.judge_result else "",
            "judge_verdict": result.judge_result.verdict if result.judge_result else "",
            "scores": result.judge_result.scores if result.judge_result else {},
            "export_format": result.export_config.format if result.export_config else "",
            "export_key": result.export_config.key if result.export_config else "",
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

    def get_batch_summary(self, batch_id: str) -> dict[str, Any]:
        batch = self._batch_repo.get_batch(batch_id)
        if batch is None:
            raise KeyError(f"Evaluation batch not found: {batch_id}")
        return {
            "batch_id": batch_id,
            "status": batch.get("status"),
            "summary": self.refresh_batch_summary(batch_id),
        }

    def compare_batches(self, baseline_batch_id: str, candidate_batch_id: str) -> dict[str, Any]:
        baseline = self.get_batch_summary(baseline_batch_id)
        candidate = self.get_batch_summary(candidate_batch_id)
        baseline_summary = baseline["summary"]
        candidate_summary = candidate["summary"]
        deltas = {}
        for key in ("pass_rate", "judge_passed_runs", "judge_failed_runs", "avg_total_tokens", "artifact_count_total"):
            baseline_value = float(baseline_summary.get(key) or 0.0)
            candidate_value = float(candidate_summary.get(key) or 0.0)
            deltas[key] = {
                "baseline": baseline_value,
                "candidate": candidate_value,
                "delta": candidate_value - baseline_value,
            }
        score_keys = sorted(
            set(dict(baseline_summary.get("avg_scores") or {}).keys())
            | set(dict(candidate_summary.get("avg_scores") or {}).keys())
        )
        deltas["avg_scores"] = {
            key: {
                "baseline": float(dict(baseline_summary.get("avg_scores") or {}).get(key) or 0.0),
                "candidate": float(dict(candidate_summary.get("avg_scores") or {}).get(key) or 0.0),
                "delta": float(dict(candidate_summary.get("avg_scores") or {}).get(key) or 0.0)
                - float(dict(baseline_summary.get("avg_scores") or {}).get(key) or 0.0),
            }
            for key in score_keys
        }
        return {
            "baseline_batch_id": baseline_batch_id,
            "candidate_batch_id": candidate_batch_id,
            "baseline": baseline_summary,
            "candidate": candidate_summary,
            "delta": deltas,
        }

    @staticmethod
    def _serialize_scenario_ref(scenario: EvalScenario) -> dict[str, Any]:
        return {
            "scenario_id": scenario.id,
            "name": scenario.name,
            "category": scenario.category,
            "sandbox": scenario.sandbox,
            "benchmark": scenario.benchmark.model_dump(mode="json") if scenario.benchmark else None,
            "workspace": scenario.workspace.model_dump(mode="json") if scenario.workspace else None,
            "judge_config": scenario.judge_config.model_dump(mode="json") if scenario.judge_config else None,
            "artifact_policy": scenario.artifact_policy.model_dump(mode="json") if scenario.artifact_policy else None,
            "export": scenario.export.model_dump(mode="json") if scenario.export else None,
        }
