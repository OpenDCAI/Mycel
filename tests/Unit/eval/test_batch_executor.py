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


class _FailingRunner:
    async def run_scenario(self, _scenario: EvalScenario) -> EvalResult:
        raise RuntimeError("runner exploded")


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
    assert repo.get_batch(batch["batch_id"])["status"] == "completed"
    assert repo.get_batch(batch["batch_id"])["summary_json"]["completed_runs"] == 1


@pytest.mark.asyncio
async def test_batch_executor_records_failed_scenario_before_reraising():
    repo = _FakeBatchRepo()
    batch_service = EvaluationBatchService(batch_repo=repo)
    batch = batch_service.create_batch(
        submitted_by_user_id="user-1",
        agent_user_id="agent-1",
        scenario_ids=["scenario-1"],
        sandbox="local",
        max_concurrent=1,
    )
    executor = EvaluationBatchExecutor(runner=_FailingRunner(), batch_service=batch_service)

    with pytest.raises(RuntimeError, match="runner exploded"):
        await executor.run_batch(batch["batch_id"], [EvalScenario(id="scenario-1", name="Scenario 1")])

    batch_run = repo.list_batch_runs(batch["batch_id"])[0]
    assert batch_run["status"] == "failed"
    assert batch_run["summary_json"] == {"error": "runner exploded"}
    assert repo.get_batch(batch["batch_id"])["status"] == "failed"


@pytest.mark.asyncio
async def test_batch_executor_marks_batch_running_before_first_scenario():
    class InspectingRunner:
        def __init__(self, repo, batch_id):
            self.repo = repo
            self.batch_id = batch_id

        async def run_scenario(self, scenario: EvalScenario) -> EvalResult:
            assert self.repo.get_batch(self.batch_id)["status"] == "running"
            return EvalResult(
                scenario_id=scenario.id,
                trajectory=RunTrajectory(
                    id=f"eval-run-{scenario.id}",
                    thread_id=f"thread-{scenario.id}",
                    user_message="",
                    status="completed",
                ),
            )

    repo = _FakeBatchRepo()
    batch_service = EvaluationBatchService(batch_repo=repo)
    batch = batch_service.create_batch(
        submitted_by_user_id="user-1",
        agent_user_id="agent-1",
        scenario_ids=["scenario-1"],
        sandbox="local",
        max_concurrent=1,
    )
    executor = EvaluationBatchExecutor(runner=InspectingRunner(repo, batch["batch_id"]), batch_service=batch_service)

    await executor.run_batch(batch["batch_id"], [EvalScenario(id="scenario-1", name="Scenario 1")])
