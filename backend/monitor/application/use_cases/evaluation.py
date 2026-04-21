"""Evaluation read and batch control boundary for Monitor."""

from __future__ import annotations

import logging
from typing import Any

from backend.monitor.infrastructure.evaluation import evaluation_execution_service, evaluation_read_service
from backend.monitor.infrastructure.evaluation.evaluation_scheduler import EvaluationJobScheduler, EvaluationJobSpec
from eval.exporter import build_batch_export

logger = logging.getLogger(__name__)


def _build_monitor_evaluation_run_fact_rows(
    metrics_rows: list[dict[str, Any]],
    *,
    judge_result: dict[str, Any] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    metrics_by_tier = {str(row.get("tier") or "").strip().lower(): row.get("metrics") or {} for row in metrics_rows}
    system_metrics = metrics_by_tier.get("system") or {}
    objective_metrics = metrics_by_tier.get("objective") or {}
    facts = [{"label": "Metric Tiers", "value": str(len(metrics_rows))}]
    for label, key in [
        ("Total tokens", "total_tokens"),
        ("LLM calls", "llm_call_count"),
        ("Tool calls", "tool_call_count"),
    ]:
        value = system_metrics.get(key)
        if value is not None:
            facts.append({"label": label, "value": str(value)})
    total_duration_ms = objective_metrics.get("total_duration_ms")
    if total_duration_ms is not None:
        duration_value = int(total_duration_ms) if float(total_duration_ms).is_integer() else total_duration_ms
        facts.append({"label": "Duration (ms)", "value": str(duration_value)})
    if judge_result:
        facts.append({"label": "Judge verdict", "value": str(judge_result.get("verdict") or "-")})
        if judge_result.get("scores"):
            first_score_key = sorted(dict(judge_result["scores"]).keys())[0]
            facts.append(
                {
                    "label": f"Judge {first_score_key}",
                    "value": str(dict(judge_result["scores"]).get(first_score_key)),
                }
            )
    if artifacts is not None:
        facts.append({"label": "Artifacts", "value": str(len(artifacts))})
    return facts


def _build_monitor_evaluation_run_row(
    run: dict[str, Any],
    metrics_rows: list[dict[str, Any]],
    *,
    judge_result: dict[str, Any] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    benchmark: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "run_id": str(run.get("id") or "") or None,
        "thread_id": str(run.get("thread_id") or "") or None,
        "status": str(run.get("status") or "") or None,
        "started_at": str(run.get("started_at") or "") or None,
        "finished_at": str(run.get("finished_at") or "") or None,
        "user_message": str(run.get("user_message") or "") or None,
        "final_response": str(run.get("final_response") or "") or None,
        "facts": _build_monitor_evaluation_run_fact_rows(metrics_rows, judge_result=judge_result, artifacts=artifacts),
        "judge_result": judge_result,
        "artifact_count": len(artifacts or []),
        "benchmark": benchmark,
    }


def get_monitor_evaluation_workbench() -> dict[str, Any]:
    store = evaluation_read_service.make_trajectory_store()
    runs = store.list_runs(limit=25)
    if not runs:
        return {
            "headline": "Evaluation Workbench",
            "summary": "No persisted evaluation runs are available yet.",
            "overview": {
                "total_runs": 0,
                "running_runs": 0,
                "completed_runs": 0,
                "failed_runs": 0,
            },
            "runs": [],
            "selected_run": None,
            "limitations": ["Create and start an evaluation batch to populate persisted runs."],
        }

    run_rows = []
    running_runs = 0
    completed_runs = 0
    failed_runs = 0
    for run in runs:
        status = str(run.get("status") or "").strip().lower()
        if status == "running":
            running_runs += 1
        elif status == "completed":
            completed_runs += 1
        elif status in {"error", "failed", "cancelled"}:
            failed_runs += 1
        run_id = str(run.get("id") or "")
        run_rows.append(
            _build_monitor_evaluation_run_row(
                run,
                store.get_metrics(run_id),
                judge_result=_dump_model(store.get_judge_result(run_id)),
                artifacts=[artifact.model_dump(mode="json") for artifact in store.get_artifacts(run_id)],
                benchmark=_dump_model(store.get_benchmark_info(run_id)),
            )
        )

    return {
        "headline": "Evaluation Workbench",
        "summary": "Recent persisted evaluation runs and their runtime state.",
        "overview": {
            "total_runs": len(run_rows),
            "running_runs": running_runs,
            "completed_runs": completed_runs,
            "failed_runs": failed_runs,
        },
        "runs": run_rows,
        "selected_run": run_rows[0],
        "limitations": [],
    }


def get_monitor_evaluation_run_detail(run_id: str) -> dict[str, Any]:
    store = evaluation_read_service.make_trajectory_store()
    run = store.get_run(run_id)
    if run is None:
        raise KeyError(f"Evaluation run not found: {run_id}")
    artifacts = [artifact.model_dump(mode="json") for artifact in store.get_artifacts(run_id)]
    judge_result = _dump_model(store.get_judge_result(run_id))
    benchmark = _dump_model(store.get_benchmark_info(run_id))
    run_row = _build_monitor_evaluation_run_row(
        run,
        store.get_metrics(run_id),
        judge_result=judge_result,
        artifacts=artifacts,
        benchmark=benchmark,
    )
    detail = {"run": run_row, "facts": run_row["facts"], "limitations": []}
    detail["batch_run"] = evaluation_read_service.make_eval_batch_service().get_batch_run_for_eval_run(run_id)
    detail["judge_result"] = judge_result
    detail["artifacts"] = artifacts
    detail["benchmark"] = benchmark
    return detail


def get_monitor_evaluation_batches(limit: int = 50) -> dict[str, Any]:
    items = evaluation_read_service.make_eval_batch_service().list_batches(limit=limit)
    return {
        "items": items,
        "count": len(items),
    }


def get_monitor_evaluation_scenarios() -> dict[str, Any]:
    items = [
        {
            "scenario_id": scenario.id,
            "name": scenario.name,
            "category": scenario.category,
            "sandbox": scenario.sandbox,
            "message_count": len(scenario.messages),
            "timeout_seconds": scenario.timeout_seconds,
            "benchmark": scenario.benchmark.model_dump(mode="json") if scenario.benchmark else None,
            "workspace": scenario.workspace.model_dump(mode="json") if scenario.workspace else None,
            "judge_type": scenario.judge_config.type if scenario.judge_config else None,
            "export_format": scenario.export.format if scenario.export else None,
        }
        for scenario in evaluation_execution_service.load_monitor_eval_scenarios()
    ]
    return {"items": items, "count": len(items)}


def create_monitor_evaluation_batch(
    *,
    submitted_by_user_id: str,
    agent_user_id: str,
    scenario_ids: list[str],
    sandbox: str,
    max_concurrent: int,
) -> dict[str, Any]:
    scenarios = evaluation_execution_service.select_monitor_eval_scenarios(list(scenario_ids), sandbox=sandbox)
    batch = evaluation_read_service.make_eval_batch_service().create_batch(
        submitted_by_user_id=submitted_by_user_id,
        agent_user_id=agent_user_id,
        scenario_ids=scenario_ids,
        sandbox=sandbox,
        max_concurrent=max_concurrent,
        scenario_refs=scenarios,
    )
    return {"batch": batch}


def start_monitor_evaluation_batch(
    batch_id: str,
    *,
    base_url: str,
    token: str,
    scheduler: EvaluationJobScheduler,
) -> dict[str, Any]:
    batch_service = evaluation_read_service.make_eval_batch_service()
    detail = batch_service.get_batch_detail(batch_id)
    batch = detail["batch"]
    config = batch.get("config_json") or {}
    scenario_ids = config.get("scenario_ids")
    sandbox = config.get("sandbox")
    max_concurrent = int(config.get("max_concurrent") or 1)
    agent_user_id = batch.get("agent_user_id")
    if not scenario_ids:
        raise ValueError("Evaluation batch is missing scenario_ids")
    if not sandbox:
        raise ValueError("Evaluation batch is missing sandbox")
    if not agent_user_id:
        raise ValueError("Evaluation batch is missing agent_user_id")
    scenarios = evaluation_execution_service.select_monitor_eval_scenarios(
        [str(scenario_id) for scenario_id in scenario_ids],
        sandbox=str(sandbox),
    )
    updated = batch_service.update_batch_status(batch_id, "running")
    scheduler.submit(
        EvaluationJobSpec(
            batch_id=batch_id,
            scenarios=scenarios,
            base_url=base_url.rstrip("/"),
            token=token,
            agent_user_id=str(agent_user_id),
            max_concurrent=max_concurrent,
        )
    )
    return {"accepted": True, "batch": updated}


def get_monitor_evaluation_batch_detail(batch_id: str) -> dict[str, Any]:
    batch_service = evaluation_read_service.make_eval_batch_service()
    detail = batch_service.get_batch_detail(batch_id)
    detail["aggregate"] = batch_service.get_batch_summary(batch_id)["summary"]
    return detail


def get_monitor_evaluation_batch_aggregate(batch_id: str) -> dict[str, Any]:
    return evaluation_read_service.make_eval_batch_service().get_batch_summary(batch_id)


def compare_monitor_evaluation_batches(*, baseline_batch_id: str, candidate_batch_id: str) -> dict[str, Any]:
    return evaluation_read_service.make_eval_batch_service().compare_batches(baseline_batch_id, candidate_batch_id)


def get_monitor_evaluation_run_artifacts(run_id: str) -> dict[str, Any]:
    store = evaluation_read_service.make_trajectory_store()
    if store.get_run(run_id) is None:
        raise KeyError(f"Evaluation run not found: {run_id}")
    return {
        "run_id": run_id,
        "artifacts": [artifact.model_dump(mode="json") for artifact in store.get_artifacts(run_id)],
        "judge_result": _dump_model(store.get_judge_result(run_id)),
        "benchmark": _dump_model(store.get_benchmark_info(run_id)),
    }


def export_monitor_evaluation_batch(batch_id: str, *, export_format: str | None = None) -> dict[str, Any]:
    batch_service = evaluation_read_service.make_eval_batch_service()
    store = evaluation_read_service.make_trajectory_store()
    detail = batch_service.get_batch_detail(batch_id)
    batch = detail["batch"]
    aggregate = batch_service.get_batch_summary(batch_id)["summary"]
    resolved_format = export_format or _resolve_batch_export_format(batch)
    run_records: list[dict[str, Any]] = []
    for batch_run in detail["runs"]:
        run_id = str(batch_run.get("eval_run_id") or "")
        if not run_id:
            continue
        run = store.get_run(run_id)
        if run is None:
            logger.warning("Skipping export for missing evaluation run %s in batch %s", run_id, batch_id)
            continue
        run_records.append(
            {
                "run_id": run_id,
                "scenario_id": batch_run.get("scenario_id"),
                "batch_run": batch_run,
                "run": {
                    "run_id": run_id,
                    "thread_id": run.get("thread_id"),
                    "status": run.get("status"),
                    "final_response": run.get("final_response"),
                },
                "judge_result": _dump_model(store.get_judge_result(run_id)),
                "artifacts": [artifact.model_dump(mode="json") for artifact in store.get_artifacts(run_id)],
                "benchmark": _dump_model(store.get_benchmark_info(run_id)),
            }
        )
    return build_batch_export(batch=batch, aggregate=aggregate, run_records=run_records, export_format=resolved_format)


def _resolve_batch_export_format(batch: dict[str, Any]) -> str:
    config = batch.get("config_json") or {}
    scenario_refs = list(config.get("scenario_refs") or [])
    for scenario_ref in scenario_refs:
        export_config = dict(scenario_ref.get("export") or {})
        export_format = str(export_config.get("format") or "").strip()
        if export_format:
            return export_format
    return "generic_json"


def _dump_model(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else dict(value)
