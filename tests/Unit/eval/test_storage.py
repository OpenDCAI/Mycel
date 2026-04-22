from eval.storage import TrajectoryStore


class _FakeEvalRepo:
    def __init__(self) -> None:
        self.header_calls: list[dict] = []
        self.finalize_calls: list[dict] = []
        self.metrics_calls: list[dict] = []
        self.metrics_rows: list[dict] = []

    def upsert_run_header(self, **payload):
        self.header_calls.append(payload)

    def finalize_run(self, **payload):
        self.finalize_calls.append(payload)

    def save_metrics(self, **payload):
        self.metrics_calls.append(payload)
        self.metrics_rows.append(
            {
                "id": payload["run_id"],
                "tier": payload["tier"],
                "timestamp": payload["timestamp"],
                "metrics_json": payload["metrics_json"],
            }
        )

    def get_metrics(self, run_id: str, tier: str | None = None):
        rows = [row for row in self.metrics_rows if row["id"] == run_id]
        if tier is not None:
            rows = [row for row in rows if row["tier"] == tier]
        return rows


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


def test_trajectory_store_round_trips_artifacts_and_judge_result() -> None:
    repo = _FakeEvalRepo()
    store = TrajectoryStore(eval_repo=repo)

    store.save_artifacts(
        "run-1",
        [
            {
                "name": "final-response",
                "kind": "submission",
                "content": "patch text",
                "metadata": {"captured": True},
            }
        ],
    )
    store.save_judge_result(
        "run-1",
        {
            "judge_type": "heuristic",
            "status": "completed",
            "verdict": "passed",
            "scores": {"resolved": 1.0},
        },
    )

    artifacts = store.get_artifacts("run-1")
    judge_result = store.get_judge_result("run-1")

    assert artifacts[0].name == "final-response"
    assert artifacts[0].content == "patch text"
    assert judge_result is not None
    assert judge_result.verdict == "passed"
