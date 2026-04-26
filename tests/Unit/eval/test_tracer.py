from eval.tracer import TrajectoryTracer


def test_trajectory_tracer_reuses_supplied_run_id() -> None:
    tracer = TrajectoryTracer(
        thread_id="thread-1",
        user_message="hello",
        run_id="run-123",
    )

    trajectory = tracer.to_trajectory()

    assert trajectory.id == "run-123"
