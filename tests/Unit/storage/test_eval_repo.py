from eval.models import LLMCallRecord, RunTrajectory, SystemMetrics, ToolCallRecord
from eval.storage import TrajectoryStore


def test_save_and_load_trajectory(tmp_path):
    db_path = tmp_path / "eval.db"
    store = TrajectoryStore(db_path)

    trajectory = RunTrajectory(
        id="run-1",
        thread_id="thread-1",
        user_message="hello",
        final_response="world",
        started_at="2026-02-24T20:00:00Z",
        finished_at="2026-02-24T20:00:01Z",
        llm_calls=[LLMCallRecord(run_id="run-1", model_name="m1", input_tokens=10, output_tokens=3, total_tokens=13)],
        tool_calls=[ToolCallRecord(run_id="run-1", tool_name="bash", success=True)],
    )

    run_id = store.save_trajectory(trajectory)
    assert run_id == "run-1"

    loaded = store.get_trajectory("run-1")
    assert loaded is not None
    assert loaded.thread_id == "thread-1"
    assert loaded.final_response == "world"
    assert len(loaded.llm_calls) == 1
    assert len(loaded.tool_calls) == 1


def test_list_runs_and_metrics(tmp_path):
    db_path = tmp_path / "eval.db"
    store = TrajectoryStore(db_path)

    t1 = RunTrajectory(id="run-a", thread_id="thread-a", user_message="a")
    t2 = RunTrajectory(id="run-b", thread_id="thread-b", user_message="b")
    store.save_trajectory(t1)
    store.save_trajectory(t2)

    all_runs = store.list_runs(limit=10)
    assert len(all_runs) == 2

    thread_a_runs = store.list_runs(thread_id="thread-a", limit=10)
    assert len(thread_a_runs) == 1
    assert thread_a_runs[0]["id"] == "run-a"

    metrics = SystemMetrics(total_tokens=42, llm_call_count=1)
    store.save_metrics("run-a", "system", metrics)

    rows = store.get_metrics("run-a")
    assert len(rows) == 1
    assert rows[0]["tier"] == "system"
    assert rows[0]["metrics"]["total_tokens"] == 42
