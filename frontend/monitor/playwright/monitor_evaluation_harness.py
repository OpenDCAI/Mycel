from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.monitor.api.http import router as monitor_router  # noqa: E402
from backend.monitor.infrastructure.web import gateway as monitor_gateway  # noqa: E402


def _scenario(
    scenario_id: str,
    *,
    name: str,
    instance_id: str,
    base_commit: str,
    rank: int,
) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "name": name,
        "category": "swe",
        "sandbox": "local",
        "message_count": 1,
        "timeout_seconds": 120,
        "benchmark": {
            "family": "SWE-bench Verified",
            "name": "SWE-bench/SWE-bench_Verified",
            "split": "test",
            "variant": "smoke",
            "instance_id": instance_id,
            "dataset_version": "91aa3ed51b709be6457e12d00300a6a596d4c6a3",
            "source_uri": "https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified",
        },
        "workspace": {
            "cwd": "/workspace/pytest",
            "repo": "pytest-dev/pytest",
            "base_commit": base_commit,
            "env": {"PYTHONUNBUFFERED": "1"},
            "setup_commands": ["python -m pip install -e ."],
        },
        "judge_type": "swe_verified_smoke",
        "export_format": "predictions_jsonl",
        "_rank": rank,
    }


class HarnessState:
    def __init__(self) -> None:
        self._batch_counter = 1
        self._run_counter = 1
        self.scenarios = [
            _scenario(
                "swe_verified_pytest_7521",
                name="pytest capfd carriage return regression",
                instance_id="pytest-dev__pytest-7521",
                base_commit="41d211c24a6781843b174379d6d6538f5c17adb9",
                rank=1,
            ),
            _scenario(
                "swe_verified_pytest_7571",
                name="pytest caplog level restore regression",
                instance_id="pytest-dev__pytest-7571",
                base_commit="422685d0bdc110547535036c1ff398b5e1c44145",
                rank=2,
            ),
        ]
        self.batches: dict[str, dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.threads: dict[str, dict[str, Any]] = {}
        self.run_order: list[str] = []
        self._seed_completed_batches()

    def _seed_completed_batches(self) -> None:
        self._create_seed_batch("batch-baseline", pass_count=1)
        self._create_seed_batch("batch-candidate", pass_count=2)

    def _create_seed_batch(self, batch_id: str, *, pass_count: int) -> None:
        scenario_refs = [self._scenario_ref(item) for item in self.scenarios]
        runs: list[dict[str, Any]] = []
        for index, scenario in enumerate(self.scenarios, start=1):
            verdict = "passed" if index <= pass_count else "failed"
            status = "completed" if verdict == "passed" else "failed"
            run_id = f"{batch_id}-run-{index}"
            thread_id = f"{batch_id}-thread-{index}"
            batch_run_id = f"{batch_id}-batch-run-{index}"
            run_detail = self._build_run_detail(
                batch_id=batch_id,
                batch_run_id=batch_run_id,
                run_id=run_id,
                thread_id=thread_id,
                scenario=scenario,
                verdict=verdict,
                status=status,
            )
            self.runs[run_id] = run_detail
            self.threads[thread_id] = self._build_thread_detail(thread_id, run_id, scenario, verdict)
            self.run_order.insert(0, run_id)
            runs.append(
                {
                    "batch_run_id": batch_run_id,
                    "scenario_id": scenario["scenario_id"],
                    "status": status,
                    "thread_id": thread_id,
                    "eval_run_id": run_id,
                    "started_at": "2026-04-21T10:00:00Z",
                    "finished_at": "2026-04-21T10:02:00Z",
                    "summary_json": self._batch_run_summary(scenario, verdict),
                }
            )

        summary = self._batch_summary(runs)
        self.batches[batch_id] = {
            "batch": {
                "batch_id": batch_id,
                "kind": "benchmark_batch",
                "status": "completed",
                "submitted_by_user_id": "owner-1",
                "agent_user_id": "agent-1",
                "created_at": "2026-04-21T09:58:00Z",
                "updated_at": "2026-04-21T10:02:00Z",
                "config_json": {
                    "scenario_ids": [item["scenario_id"] for item in self.scenarios],
                    "sandbox": "local",
                    "max_concurrent": 2,
                    "scenario_refs": scenario_refs,
                },
                "summary_json": summary,
            },
            "runs": runs,
        }

    def _scenario_ref(self, scenario: dict[str, Any]) -> dict[str, Any]:
        return {
            "scenario_id": scenario["scenario_id"],
            "name": scenario["name"],
            "category": scenario["category"],
            "sandbox": scenario["sandbox"],
            "benchmark": scenario["benchmark"],
            "workspace": scenario["workspace"],
            "judge_config": {"type": scenario["judge_type"], "config": {"profile_id": "swe_verified_smoke"}},
            "export": {
                "format": scenario["export_format"],
                "key": "predictions_path",
                "config": {"profile": "swe_verified_smoke"},
            },
        }

    def _batch_run_summary(self, scenario: dict[str, Any], verdict: str) -> dict[str, Any]:
        return {
            "instance_id": scenario["benchmark"]["instance_id"],
            "benchmark_family": scenario["benchmark"]["family"],
            "benchmark_split": scenario["benchmark"]["split"],
            "judge_type": scenario["judge_type"],
            "judge_verdict": verdict,
            "export_format": scenario["export_format"],
            "export_key": "predictions_path",
            "artifact_count": 3,
            "total_tokens": 1200 if verdict == "passed" else 1500,
        }

    def _batch_summary(self, runs: list[dict[str, Any]]) -> dict[str, Any]:
        total_runs = len(runs)
        completed_runs = sum(1 for row in runs if row["status"] == "completed")
        failed_runs = sum(1 for row in runs if row["status"] == "failed")
        passed_runs = sum(1 for row in runs if row.get("summary_json", {}).get("judge_verdict") == "passed")
        failed_judges = sum(1 for row in runs if row.get("summary_json", {}).get("judge_verdict") == "failed")
        total_tokens = sum(int(row.get("summary_json", {}).get("total_tokens") or 0) for row in runs)
        artifacts = sum(int(row.get("summary_json", {}).get("artifact_count") or 0) for row in runs)
        return {
            "total_runs": total_runs,
            "running_runs": 0,
            "completed_runs": completed_runs,
            "failed_runs": failed_runs,
            "judge_passed_runs": passed_runs,
            "judge_failed_runs": failed_judges,
            "pass_rate": passed_runs / total_runs if total_runs else 0.0,
            "avg_total_tokens": total_tokens / total_runs if total_runs else 0.0,
            "artifact_count_total": artifacts,
            "avg_scores": {"resolved": passed_runs / total_runs if total_runs else 0.0},
            "benchmark_families": ["SWE-bench Verified"],
            "benchmark_splits": ["test"],
        }

    def _build_run_detail(
        self,
        *,
        batch_id: str,
        batch_run_id: str,
        run_id: str,
        thread_id: str,
        scenario: dict[str, Any],
        verdict: str,
        status: str,
    ) -> dict[str, Any]:
        benchmark = copy.deepcopy(scenario["benchmark"])
        judge_result = {
            "judge_type": scenario["judge_type"],
            "status": "completed",
            "verdict": verdict,
            "rationale": "Smoke harness verdict generated by the monitor Playwright fixture.",
            "scores": {"resolved": 1.0 if verdict == "passed" else 0.0},
            "metadata": {"fixture": True},
        }
        artifacts = [
            {
                "name": "model_patch.diff",
                "kind": "patch",
                "mime_type": "text/x-diff",
                "content": "diff --git a/testing/test_capture.py b/testing/test_capture.py\n+    assert out.endswith('\\r')\n",
                "metadata": {"instance_id": benchmark["instance_id"]},
            },
            {
                "name": "test_output.log",
                "kind": "test_log",
                "mime_type": "text/plain",
                "content": "pytest testing/test_capture.py -q\n1 passed\n" if verdict == "passed" else "pytest testing/test_capture.py -q\n1 failed\n",
                "metadata": {"verdict": verdict},
            },
            {
                "name": "judge_result.json",
                "kind": "judge_result",
                "mime_type": "application/json",
                "content": None,
                "metadata": judge_result,
            },
        ]
        facts = [
            {"label": "Metric Tiers", "value": "2"},
            {"label": "Total tokens", "value": "1200" if verdict == "passed" else "1500"},
            {"label": "LLM calls", "value": "3"},
            {"label": "Tool calls", "value": "2"},
            {"label": "Judge verdict", "value": verdict},
            {"label": "Artifacts", "value": str(len(artifacts))},
        ]
        return {
            "run": {
                "run_id": run_id,
                "thread_id": thread_id,
                "status": status,
                "started_at": "2026-04-21T10:00:00Z",
                "finished_at": "2026-04-21T10:02:00Z",
                "user_message": f"Fix {benchmark['instance_id']}",
                "final_response": "Prepared a patch, ran focused tests, and summarized the result.",
                "artifact_count": len(artifacts),
                "benchmark": benchmark,
                "judge_result": judge_result,
            },
            "facts": facts,
            "batch_run": {
                "batch_run_id": batch_run_id,
                "batch_id": batch_id,
                "scenario_id": scenario["scenario_id"],
            },
            "limitations": [],
            "judge_result": judge_result,
            "artifacts": artifacts,
            "benchmark": benchmark,
        }

    def _build_thread_detail(self, thread_id: str, run_id: str, scenario: dict[str, Any], verdict: str) -> dict[str, Any]:
        return {
            "thread": {"thread_id": thread_id},
            "trajectory": {
                "run_id": run_id,
                "conversation": [
                    {"role": "user", "content": f"Investigate {scenario['benchmark']['instance_id']}"},
                    {"role": "assistant", "content": "Inspecting pytest capture behavior and preparing a minimal patch."},
                ],
                "events": [
                    {
                        "seq": 1,
                        "run_id": run_id,
                        "event_type": "assistant_text",
                        "actor": "assistant",
                        "summary": "Inspecting repository checkout",
                        "payload": {"content": "Opened testing/test_capture.py"},
                    },
                    {
                        "seq": 2,
                        "run_id": run_id,
                        "event_type": "tool_call",
                        "actor": "tool",
                        "summary": "exec_command",
                        "payload": {"cmd": "pytest testing/test_capture.py -q"},
                    },
                    {
                        "seq": 3,
                        "run_id": run_id,
                        "event_type": "tool_result",
                        "actor": "tool",
                        "summary": "pytest result",
                        "payload": {"content": "1 passed" if verdict == "passed" else "1 failed"},
                    },
                ],
            },
        }

    def _run_row(self, run_id: str) -> dict[str, Any]:
        detail = self.runs[run_id]
        run = detail["run"]
        return {
            "run_id": run["run_id"],
            "thread_id": run["thread_id"],
            "status": run["status"],
            "started_at": run["started_at"],
            "finished_at": run["finished_at"],
            "user_message": run["user_message"],
            "facts": detail["facts"],
        }

    def workbench(self) -> dict[str, Any]:
        run_rows = [self._run_row(run_id) for run_id in self.run_order[:6]]
        return {
            "headline": "Evaluation Workbench",
            "summary": "Harness-backed monitor evaluation workbench.",
            "overview": {
                "total_runs": len(run_rows),
                "running_runs": 0,
                "completed_runs": sum(1 for row in run_rows if row["status"] == "completed"),
                "failed_runs": sum(1 for row in run_rows if row["status"] == "failed"),
            },
            "runs": run_rows,
            "selected_run": run_rows[0] if run_rows else None,
            "limitations": [],
        }

    def list_batches(self, limit: int = 50) -> dict[str, Any]:
        items = [copy.deepcopy(self.batches[batch_id]["batch"]) for batch_id in sorted(self.batches.keys())]
        items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return {"items": items[:limit], "count": min(len(items), limit)}

    def batch_detail(self, batch_id: str) -> dict[str, Any]:
        if batch_id not in self.batches:
            raise KeyError(f"Evaluation batch not found: {batch_id}")
        payload = copy.deepcopy(self.batches[batch_id])
        payload["aggregate"] = copy.deepcopy(payload["batch"]["summary_json"])
        return payload

    def batch_aggregate(self, batch_id: str) -> dict[str, Any]:
        detail = self.batch_detail(batch_id)
        return {
            "batch_id": batch_id,
            "status": detail["batch"]["status"],
            "summary": copy.deepcopy(detail["batch"]["summary_json"]),
        }

    def run_detail(self, run_id: str) -> dict[str, Any]:
        if run_id not in self.runs:
            raise KeyError(f"Evaluation run not found: {run_id}")
        return copy.deepcopy(self.runs[run_id])

    def run_artifacts(self, run_id: str) -> dict[str, Any]:
        detail = self.run_detail(run_id)
        return {
            "run_id": run_id,
            "artifacts": detail["artifacts"],
            "judge_result": detail["judge_result"],
            "benchmark": detail["benchmark"],
        }

    def thread_detail(self, thread_id: str) -> dict[str, Any]:
        if thread_id not in self.threads:
            raise KeyError(f"Thread not found: {thread_id}")
        return copy.deepcopy(self.threads[thread_id])

    def create_batch(self, *, submitted_by_user_id: str, agent_user_id: str, scenario_ids: list[str], sandbox: str, max_concurrent: int) -> dict[str, Any]:
        catalog = {item["scenario_id"]: item for item in self.scenarios}
        scenario_refs = []
        for scenario_id in scenario_ids:
            if scenario_id not in catalog:
                raise KeyError(f"Evaluation scenarios not found: {scenario_id}")
            scenario_refs.append(self._scenario_ref(catalog[scenario_id]))
        batch_id = f"eval-batch-created-{self._batch_counter:04d}"
        self._batch_counter += 1
        runs = []
        for index, scenario_id in enumerate(scenario_ids, start=1):
            scenario = catalog[scenario_id]
            runs.append(
                {
                    "batch_run_id": f"{batch_id}-batch-run-{index}",
                    "scenario_id": scenario_id,
                    "status": "pending",
                    "thread_id": None,
                    "eval_run_id": None,
                    "started_at": None,
                    "finished_at": None,
                    "summary_json": {
                        "instance_id": scenario["benchmark"]["instance_id"],
                        "benchmark_family": scenario["benchmark"]["family"],
                        "benchmark_split": scenario["benchmark"]["split"],
                        "judge_type": scenario["judge_type"],
                        "export_format": scenario["export_format"],
                        "artifact_count": 0,
                    },
                }
            )
        summary = {
            "total_runs": len(runs),
            "running_runs": 0,
            "completed_runs": 0,
            "failed_runs": 0,
            "judge_passed_runs": 0,
            "judge_failed_runs": 0,
            "pass_rate": 0.0,
            "avg_total_tokens": 0.0,
            "artifact_count_total": 0,
            "avg_scores": {},
            "benchmark_families": ["SWE-bench Verified"],
            "benchmark_splits": ["test"],
        }
        self.batches[batch_id] = {
            "batch": {
                "batch_id": batch_id,
                "kind": "benchmark_batch",
                "status": "pending",
                "submitted_by_user_id": submitted_by_user_id,
                "agent_user_id": agent_user_id,
                "created_at": "2026-04-21T11:00:00Z",
                "updated_at": "2026-04-21T11:00:00Z",
                "config_json": {
                    "scenario_ids": scenario_ids,
                    "sandbox": sandbox,
                    "max_concurrent": max_concurrent,
                    "scenario_refs": scenario_refs,
                },
                "summary_json": summary,
            },
            "runs": runs,
        }
        return {"batch": {"batch_id": batch_id}}

    def start_batch(self, *, batch_id: str) -> dict[str, Any]:
        if batch_id not in self.batches:
            raise KeyError(f"Evaluation batch not found: {batch_id}")
        detail = self.batches[batch_id]
        if detail["batch"]["status"] != "pending":
            return {"accepted": False, "batch": copy.deepcopy(detail["batch"])}

        for index, run in enumerate(detail["runs"], start=1):
            scenario = next(item for item in self.scenarios if item["scenario_id"] == run["scenario_id"])
            verdict = "passed" if index == 1 else "failed"
            status = "completed" if verdict == "passed" else "failed"
            run_id = f"created-run-{self._run_counter:04d}"
            thread_id = f"created-thread-{self._run_counter:04d}"
            self._run_counter += 1
            run_detail = self._build_run_detail(
                batch_id=batch_id,
                batch_run_id=run["batch_run_id"],
                run_id=run_id,
                thread_id=thread_id,
                scenario=scenario,
                verdict=verdict,
                status=status,
            )
            self.runs[run_id] = run_detail
            self.threads[thread_id] = self._build_thread_detail(thread_id, run_id, scenario, verdict)
            self.run_order.insert(0, run_id)
            run.update(
                {
                    "status": status,
                    "thread_id": thread_id,
                    "eval_run_id": run_id,
                    "started_at": "2026-04-21T11:01:00Z",
                    "finished_at": "2026-04-21T11:03:00Z",
                    "summary_json": self._batch_run_summary(scenario, verdict),
                }
            )

        detail["batch"]["status"] = "completed"
        detail["batch"]["updated_at"] = "2026-04-21T11:03:00Z"
        detail["batch"]["summary_json"] = self._batch_summary(detail["runs"])
        return {"accepted": True, "batch": copy.deepcopy(detail["batch"])}

    def compare_batches(self, baseline_batch_id: str, candidate_batch_id: str) -> dict[str, Any]:
        baseline = self.batch_detail(baseline_batch_id)["batch"]["summary_json"]
        candidate = self.batch_detail(candidate_batch_id)["batch"]["summary_json"]

        def _metric(key: str) -> dict[str, float]:
            baseline_value = float(baseline.get(key) or 0.0)
            candidate_value = float(candidate.get(key) or 0.0)
            return {
                "baseline": baseline_value,
                "candidate": candidate_value,
                "delta": candidate_value - baseline_value,
            }

        return {
            "baseline_batch_id": baseline_batch_id,
            "candidate_batch_id": candidate_batch_id,
            "baseline": copy.deepcopy(baseline),
            "candidate": copy.deepcopy(candidate),
            "delta": {
                "pass_rate": _metric("pass_rate"),
                "judge_passed_runs": _metric("judge_passed_runs"),
                "judge_failed_runs": _metric("judge_failed_runs"),
                "avg_total_tokens": _metric("avg_total_tokens"),
                "artifact_count_total": _metric("artifact_count_total"),
                "avg_scores": {
                    "resolved": {
                        "baseline": float((baseline.get("avg_scores") or {}).get("resolved") or 0.0),
                        "candidate": float((candidate.get("avg_scores") or {}).get("resolved") or 0.0),
                        "delta": float((candidate.get("avg_scores") or {}).get("resolved") or 0.0)
                        - float((baseline.get("avg_scores") or {}).get("resolved") or 0.0),
                    }
                },
            },
        }

    def export_batch(self, batch_id: str, export_format: str | None = None) -> dict[str, Any]:
        detail = self.batch_detail(batch_id)
        resolved_format = export_format or "predictions_jsonl"
        run_records = []
        for run in detail["runs"]:
            run_id = run.get("eval_run_id")
            if not run_id:
                continue
            run_detail = self.run_detail(run_id)
            run_records.append(
                {
                    "scenario_id": run["scenario_id"],
                    "run_id": run_id,
                    "benchmark": run_detail["benchmark"],
                    "judge_result": run_detail["judge_result"],
                    "artifacts": run_detail["artifacts"],
                    "final_response": run_detail["run"]["final_response"],
                }
            )
        return {
            "batch_id": batch_id,
            "format": resolved_format,
            "aggregate": detail["batch"]["summary_json"],
            "run_records": run_records,
        }


STATE = HarnessState()


def _patch_gateway() -> None:
    async def _thread_detail(_app, thread_id: str) -> dict[str, Any]:
        return STATE.thread_detail(thread_id)

    monitor_gateway.get_evaluation_workbench = STATE.workbench
    monitor_gateway.get_evaluation_batches = lambda limit=50: STATE.list_batches(limit=limit)
    monitor_gateway.get_evaluation_scenarios = lambda: {"items": copy.deepcopy(STATE.scenarios), "count": len(STATE.scenarios)}
    monitor_gateway.get_evaluation_batch_detail = STATE.batch_detail
    monitor_gateway.get_evaluation_batch_aggregate = STATE.batch_aggregate
    monitor_gateway.get_evaluation_run_detail = STATE.run_detail
    monitor_gateway.get_evaluation_run_artifacts = STATE.run_artifacts
    monitor_gateway.compare_evaluation_batches = (
        lambda *, baseline_batch_id, candidate_batch_id: STATE.compare_batches(baseline_batch_id, candidate_batch_id)
    )
    monitor_gateway.export_evaluation_batch = lambda *, batch_id, export_format=None: STATE.export_batch(batch_id, export_format)
    monitor_gateway.create_evaluation_batch = (
        lambda *, submitted_by_user_id, agent_user_id, scenario_ids, sandbox, max_concurrent: STATE.create_batch(
            submitted_by_user_id=submitted_by_user_id,
            agent_user_id=agent_user_id,
            scenario_ids=scenario_ids,
            sandbox=sandbox,
            max_concurrent=max_concurrent,
        )
    )
    monitor_gateway.start_evaluation_batch = (
        lambda *, batch_id, base_url, token, schedule_task: STATE.start_batch(batch_id=batch_id)
    )
    monitor_gateway.get_thread_detail = _thread_detail


def create_app() -> FastAPI:
    _patch_gateway()
    app = FastAPI(title="Monitor Evaluation Playwright Harness")
    app.include_router(monitor_router.router)
    app.dependency_overrides[monitor_router.get_current_user_id] = lambda: "owner-1"
    return app


app = create_app()


if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8001
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
