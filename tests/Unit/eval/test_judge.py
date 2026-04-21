import json

import pytest

from eval.judge import build_judge
from eval.models import EvalResult, EvalScenario, JudgeConfig, RunTrajectory


@pytest.mark.asyncio
async def test_heuristic_judge_scores_expected_behaviors():
    judge = build_judge(JudgeConfig(type="heuristic", config={}))
    scenario = EvalScenario(
        id="scenario-1",
        name="Scenario 1",
        expected_behaviors=["alpha", "beta"],
    )
    result = EvalResult(
        scenario_id="scenario-1",
        trajectory=RunTrajectory(thread_id="thread-1", user_message="hello", final_response="alpha beta done"),
    )

    judged = await judge.evaluate(scenario, result)

    assert judged.verdict == "passed"
    assert judged.scores["resolved"] == 1.0


@pytest.mark.asyncio
async def test_command_judge_parses_json_stdout(tmp_path):
    judge = build_judge(
        JudgeConfig(
            type="command",
            config={
                "command": [
                    "python",
                    "-c",
                    "import json,sys; payload=json.load(sys.stdin); print(json.dumps({'status':'completed','verdict':'passed','scores':{'resolved':1.0},'metadata':{'scenario_id':payload['scenario']['id']}}))",
                ]
            },
        )
    )
    scenario = EvalScenario(id="scenario-1", name="Scenario 1")
    result = EvalResult(
        scenario_id="scenario-1",
        trajectory=RunTrajectory(thread_id="thread-1", user_message="hello", final_response="done"),
    )

    judged = await judge.evaluate(scenario, result)

    assert judged.verdict == "passed"
    assert judged.metadata == {"scenario_id": "scenario-1"}


@pytest.mark.asyncio
async def test_command_judge_raises_on_non_zero_exit():
    judge = build_judge(
        JudgeConfig(
            type="command",
            config={"command": ["python", "-c", "import sys; sys.stderr.write('nope'); sys.exit(2)"]},
        )
    )
    scenario = EvalScenario(id="scenario-1", name="Scenario 1")
    result = EvalResult(
        scenario_id="scenario-1",
        trajectory=RunTrajectory(thread_id="thread-1", user_message="hello", final_response="done"),
    )

    with pytest.raises(RuntimeError, match="Judge command failed"):
        await judge.evaluate(scenario, result)
