"""Evaluation scenario and runner port for Monitor."""

from __future__ import annotations

from pathlib import Path

from backend.monitor.infrastructure.evaluation import evaluation_storage_service
from eval.batch_executor import EvaluationBatchExecutor
from eval.batch_service import EvaluationBatchService
from eval.harness.client import EvalClient
from eval.harness.runner import EvalRunner
from eval.harness.scenario import load_scenarios_from_dir
from eval.models import EvalScenario

EVAL_SCENARIO_DIR = Path(__file__).resolve().parents[4] / "eval" / "scenarios"


def load_monitor_eval_scenarios() -> list[EvalScenario]:
    return load_scenarios_from_dir(EVAL_SCENARIO_DIR)


def select_monitor_eval_scenarios(scenario_ids: list[str], *, sandbox: str) -> list[EvalScenario]:
    catalog = {scenario.id: scenario for scenario in load_monitor_eval_scenarios()}
    missing = [scenario_id for scenario_id in scenario_ids if scenario_id not in catalog]
    if missing:
        raise KeyError(f"Evaluation scenarios not found: {', '.join(missing)}")
    return [catalog[scenario_id].model_copy(update={"sandbox": sandbox}) for scenario_id in scenario_ids]


async def run_monitor_evaluation_batch(
    *,
    batch_id: str,
    scenarios: list[EvalScenario],
    execution_base_url: str,
    token: str,
    agent_user_id: str,
    batch_service: EvaluationBatchService,
) -> None:
    client = EvalClient(base_url=execution_base_url, token=token)
    try:
        runner = EvalRunner(
            client=client,
            agent_user_id=agent_user_id,
            store=evaluation_storage_service.make_trajectory_store(),
        )
        executor = EvaluationBatchExecutor(runner=runner, batch_service=batch_service)
        await executor.run_batch(batch_id, scenarios)
    finally:
        await client.close()
