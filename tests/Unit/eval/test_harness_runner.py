import pytest

from eval.harness.runner import EvalRunner
from eval.models import EvalScenario, ScenarioMessage, TrajectoryCapture


class _RuntimeFailingClient:
    async def create_thread(self, *, agent_user_id: str, sandbox: str) -> str:
        return "thread-1"

    async def run_message(self, _thread_id: str, _message: str, enable_trajectory: bool = True) -> TrajectoryCapture:
        return TrajectoryCapture(text_chunks=["ok"], terminal_event="done")

    async def get_runtime(self, _thread_id: str) -> dict:
        raise RuntimeError("runtime unavailable")

    async def delete_thread(self, _thread_id: str) -> None:
        return None


class _DeleteFailingClient:
    async def create_thread(self, *, agent_user_id: str, sandbox: str) -> str:
        return "thread-1"

    async def run_message(self, _thread_id: str, _message: str, enable_trajectory: bool = True) -> TrajectoryCapture:
        return TrajectoryCapture(text_chunks=["ok"], terminal_event="done")

    async def get_runtime(self, _thread_id: str) -> dict:
        return {"context": {"usage_percent": 1.0}}

    async def delete_thread(self, _thread_id: str) -> None:
        raise RuntimeError("delete failed")


@pytest.mark.asyncio
async def test_eval_runner_fails_loudly_when_runtime_status_is_unavailable():
    runner = EvalRunner(client=_RuntimeFailingClient(), agent_user_id="agent-1")

    with pytest.raises(RuntimeError, match="runtime unavailable"):
        await runner.run_scenario(EvalScenario(id="scenario-1", name="Scenario 1", messages=[ScenarioMessage(content="hello")]))


@pytest.mark.asyncio
async def test_eval_runner_fails_loudly_when_thread_cleanup_fails():
    runner = EvalRunner(client=_DeleteFailingClient(), agent_user_id="agent-1")

    with pytest.raises(RuntimeError, match="delete failed"):
        await runner.run_scenario(EvalScenario(id="scenario-1", name="Scenario 1", messages=[ScenarioMessage(content="hello")]))
