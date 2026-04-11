import pytest

from eval.batch_executor import EvaluationBatchExecutor
from eval.batch_service import EvaluationBatchService
from eval.models import EvalResult, EvalScenario, RunTrajectory
from tests.Unit.eval.test_batch_service import _FakeBatchRepo


class _FakeRunner:
    async def run_scenario(self, scenario: EvalScenario) -> EvalResult:
        return EvalResult(
            scenario_id=scenario.id,
            trajectory=RunTrajectory(
                id=f"eval-run-{scenario.id}",
                thread_id=f"thread-{scenario.id}",
                user_message=scenario.messages[0].content if scenario.messages else "",
                status="completed",
            ),
        )


@pytest.mark.asyncio
async def test_batch_executor_runs_scenarios_and_records_results():
    repo = _FakeBatchRepo()
    batch_service = EvaluationBatchService(batch_repo=repo)
    batch = batch_service.create_batch(
        submitted_by_user_id="user-1",
        agent_user_id="agent-1",
        scenario_ids=["scenario-1"],
        sandbox="local",
        max_concurrent=1,
    )
    executor = EvaluationBatchExecutor(runner=_FakeRunner(), batch_service=batch_service)

    results = await executor.run_batch(batch["batch_id"], [EvalScenario(id="scenario-1", name="Scenario 1")])
    batch_run = repo.list_batch_runs(batch["batch_id"])[0]

    assert [result.scenario_id for result in results] == ["scenario-1"]
    assert batch_run["eval_run_id"] == "eval-run-scenario-1"
    assert repo.get_batch(batch["batch_id"])["summary_json"]["completed_runs"] == 1
