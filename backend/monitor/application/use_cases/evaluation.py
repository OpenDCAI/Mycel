from __future__ import annotations

from typing import Any

from backend.monitor.infrastructure.evaluation import evaluation_execution_service, evaluation_storage_service
from backend.monitor.infrastructure.evaluation.evaluation_scheduler import EvaluationJobScheduler, EvaluationJobSpec


def _build_monitor_evaluation_run_fact_rows(metrics_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
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
    return facts


def _build_monitor_evaluation_run_row(run: dict[str, Any], metrics_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "run_id": str(run.get("id") or "") or None,
        "thread_id": str(run.get("thread_id") or "") or None,
        "status": str(run.get("status") or "") or None,
        "started_at": str(run.get("started_at") or "") or None,
        "finished_at": str(run.get("finished_at") or "") or None,
        "user_message": str(run.get("user_message") or "") or None,
        "facts": _build_monitor_evaluation_run_fact_rows(metrics_rows),
    }


def get_monitor_evaluation_workbench() -> dict[str, Any]:
    store = evaluation_storage_service.make_trajectory_store()
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
        run_rows.append(_build_monitor_evaluation_run_row(run, store.get_metrics(str(run.get("id") or ""))))

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
    store = evaluation_storage_service.make_trajectory_store()
    run = store.get_run(run_id)
    if run is None:
        raise KeyError(f"Evaluation run not found: {run_id}")
    run_row = _build_monitor_evaluation_run_row(run, store.get_metrics(run_id))
    detail = {"run": run_row, "facts": run_row["facts"], "limitations": []}
    detail["batch_run"] = evaluation_storage_service.make_eval_batch_service().get_batch_run_for_eval_run(run_id)
    return detail


def get_monitor_evaluation_batches(limit: int = 50) -> dict[str, Any]:
    items = evaluation_storage_service.make_eval_batch_service().list_batches(limit=limit)
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
    batch = evaluation_storage_service.make_eval_batch_service().create_batch(
        submitted_by_user_id=submitted_by_user_id,
        agent_user_id=agent_user_id,
        scenario_ids=scenario_ids,
        sandbox=sandbox,
        max_concurrent=max_concurrent,
    )
    return {"batch": batch}


def start_monitor_evaluation_batch(
    batch_id: str,
    *,
    execution_base_url: str,
    token: str,
    scheduler: EvaluationJobScheduler,
) -> dict[str, Any]:
    batch_service = evaluation_storage_service.make_eval_batch_service()
    detail = batch_service.get_batch_detail(batch_id)
    batch = detail["batch"]
    config = batch.get("config_json") or {}
    scenario_ids = config.get("scenario_ids")
    sandbox = config.get("sandbox")
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
            execution_base_url=execution_base_url.rstrip("/"),
            token=token,
            agent_user_id=str(agent_user_id),
        )
    )
    return {"accepted": True, "batch": updated}


def get_monitor_evaluation_batch_detail(batch_id: str) -> dict[str, Any]:
    return evaluation_storage_service.make_eval_batch_service().get_batch_detail(batch_id)
