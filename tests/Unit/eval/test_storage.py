from eval.storage import TrajectoryStore


class _FakeEvalRepo:
    def __init__(self) -> None:
        self.header_calls: list[dict] = []
        self.finalize_calls: list[dict] = []

    def upsert_run_header(self, **payload):
        self.header_calls.append(payload)

    def finalize_run(self, **payload):
        self.finalize_calls.append(payload)


def test_trajectory_store_exposes_upsert_run_header() -> None:
    repo = _FakeEvalRepo()
    store = TrajectoryStore(eval_repo=repo)

    store.upsert_run_header(
        run_id="run-1",
        thread_id="thread-1",
        started_at="2026-04-08T12:00:00Z",
        user_message="hello",
        status="running",
    )

    assert repo.header_calls == [
        {
            "run_id": "run-1",
            "thread_id": "thread-1",
            "started_at": "2026-04-08T12:00:00Z",
            "user_message": "hello",
            "status": "running",
        }
    ]


def test_trajectory_store_exposes_finalize_run() -> None:
    repo = _FakeEvalRepo()
    store = TrajectoryStore(eval_repo=repo)

    store.finalize_run(
        run_id="run-1",
        finished_at="2026-04-08T12:01:00Z",
        final_response="done",
        status="completed",
        run_tree_json="{}",
        trajectory_json='{"id":"run-1"}',
    )

    assert repo.finalize_calls == [
        {
            "run_id": "run-1",
            "finished_at": "2026-04-08T12:01:00Z",
            "final_response": "done",
            "status": "completed",
            "run_tree_json": "{}",
            "trajectory_json": '{"id":"run-1"}',
        }
    ]
