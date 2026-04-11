from eval.batch_models import EvaluationBatch, EvaluationBatchRun
from eval.batch_service import EvaluationBatchService
from eval.models import EvalResult, RunTrajectory, SystemMetrics


def _batch_row(*, batch_id: str = "batch-1", status: str = "pending") -> dict:
    return {
        "batch_id": batch_id,
        "kind": "scenario_batch",
        "submitted_by_user_id": "user-1",
        "agent_user_id": "agent-1",
        "config_json": {"sandbox": "local"},
        "status": status,
        "created_at": "2026-04-11T00:00:00Z",
        "updated_at": "2026-04-11T00:00:00Z",
        "summary_json": {},
    }


def _batch_run_row(batch_run_id: str, *, batch_id: str = "batch-1", status: str = "pending") -> dict:
    return {
        "batch_run_id": batch_run_id,
        "batch_id": batch_id,
        "item_key": batch_run_id,
        "scenario_id": f"scenario-{batch_run_id}",
        "status": status,
        "thread_id": None,
        "eval_run_id": None,
        "started_at": None,
        "finished_at": None,
        "summary_json": {},
    }


def test_evaluation_batch_defaults_to_pending():
    batch = EvaluationBatch(
        batch_id="batch-1",
        kind="scenario_batch",
        submitted_by_user_id="user-1",
        agent_user_id="agent-1",
        config_json={"sandbox": "local", "scenario_ids": ["s1"]},
    )

    assert batch.status == "pending"
    assert batch.summary_json["total_runs"] == 0


def test_evaluation_batch_run_defaults_to_pending():
    batch_run = EvaluationBatchRun(
        batch_run_id="batch-run-1",
        batch_id="batch-1",
        item_key="s1",
        scenario_id="scenario-1",
    )

    assert batch_run.status == "pending"
    assert batch_run.thread_id is None
    assert batch_run.eval_run_id is None


class _FakeBatchRepo:
    def __init__(self) -> None:
        self.batches: dict[str, dict] = {}
        self.batch_runs: dict[str, dict] = {}

    def create_batch(self, batch: dict) -> dict:
        self.batches[batch["batch_id"]] = dict(batch)
        return dict(batch)

    def get_batch(self, batch_id: str) -> dict | None:
        row = self.batches.get(batch_id)
        return dict(row) if row is not None else None

    def list_batches(self, limit: int = 50) -> list[dict]:
        rows = list(self.batches.values())
        return [dict(row) for row in rows[:limit]]

    def update_batch(self, batch_id: str, **fields) -> dict | None:
        row = self.batches.get(batch_id)
        if row is None:
            return None
        row.update(fields)
        return dict(row)

    def create_batch_run(self, batch_run: dict) -> dict:
        self.batch_runs[batch_run["batch_run_id"]] = dict(batch_run)
        return dict(batch_run)

    def list_batch_runs(self, batch_id: str) -> list[dict]:
        rows = [row for row in self.batch_runs.values() if row["batch_id"] == batch_id]
        return [dict(row) for row in rows]

    def get_batch_run_by_eval_run_id(self, eval_run_id: str) -> dict | None:
        row = next((row for row in self.batch_runs.values() if row.get("eval_run_id") == eval_run_id), None)
        return dict(row) if row is not None else None

    def update_batch_run(self, batch_run_id: str, **fields) -> dict | None:
        row = self.batch_runs.get(batch_run_id)
        if row is None:
            return None
        row.update(fields)
        return dict(row)


def test_batch_service_creates_batch_and_runs():
    repo = _FakeBatchRepo()
    service = EvaluationBatchService(batch_repo=repo)

    batch = service.create_batch(
        submitted_by_user_id="user-1",
        agent_user_id="agent-1",
        scenario_ids=["s1", "s2"],
        sandbox="local",
        max_concurrent=2,
    )

    assert batch["summary_json"]["total_runs"] == 2
    assert len(repo.list_batch_runs(batch["batch_id"])) == 2


def test_batch_service_recomputes_summary():
    repo = _FakeBatchRepo()
    service = EvaluationBatchService(batch_repo=repo)

    batch = repo.create_batch(_batch_row(status="running"))
    repo.create_batch_run(_batch_run_row("run-1", batch_id=batch["batch_id"], status="completed"))
    repo.create_batch_run(_batch_run_row("run-2", batch_id=batch["batch_id"], status="running"))

    summary = service.refresh_batch_summary(batch["batch_id"])
    assert summary["completed_runs"] == 1
    assert summary["running_runs"] == 1


def test_batch_service_links_batch_run_to_eval_run_and_refreshes_summary():
    repo = _FakeBatchRepo()
    service = EvaluationBatchService(batch_repo=repo)
    batch = service.create_batch(
        submitted_by_user_id="user-1",
        agent_user_id="agent-1",
        scenario_ids=["s1"],
        sandbox="local",
        max_concurrent=1,
    )
    batch_run = repo.list_batch_runs(batch["batch_id"])[0]

    updated = service.link_batch_run_to_eval_run(
        batch_run["batch_run_id"],
        thread_id="thread-1",
        eval_run_id="eval-run-1",
        status="completed",
    )
    summary = repo.get_batch(batch["batch_id"])["summary_json"]

    assert updated["thread_id"] == "thread-1"
    assert updated["eval_run_id"] == "eval-run-1"
    assert updated["finished_at"]
    assert summary["completed_runs"] == 1


def test_batch_service_marks_batch_run_running_with_started_at():
    repo = _FakeBatchRepo()
    service = EvaluationBatchService(batch_repo=repo)
    batch = service.create_batch(
        submitted_by_user_id="user-1",
        agent_user_id="agent-1",
        scenario_ids=["s1"],
        sandbox="local",
        max_concurrent=1,
    )
    batch_run = repo.list_batch_runs(batch["batch_id"])[0]

    updated = service.mark_batch_run_running(batch_run["batch_run_id"], thread_id="thread-1")

    assert updated["status"] == "running"
    assert updated["thread_id"] == "thread-1"
    assert updated["started_at"]


def test_batch_service_records_eval_result_for_matching_scenario():
    repo = _FakeBatchRepo()
    service = EvaluationBatchService(batch_repo=repo)
    batch = service.create_batch(
        submitted_by_user_id="user-1",
        agent_user_id="agent-1",
        scenario_ids=["scenario-1"],
        sandbox="local",
        max_concurrent=1,
    )
    result = EvalResult(
        scenario_id="scenario-1",
        trajectory=RunTrajectory(
            id="eval-run-1",
            thread_id="thread-1",
            user_message="hello",
            status="completed",
        ),
        system_metrics=SystemMetrics(total_tokens=42, tool_call_count=3),
    )

    updated = service.record_eval_result(batch["batch_id"], result)

    assert updated["eval_run_id"] == "eval-run-1"
    assert updated["thread_id"] == "thread-1"
    assert updated["status"] == "completed"
    assert updated["summary_json"] == {"total_tokens": 42, "tool_call_count": 3}


def test_batch_service_records_eval_error_for_matching_scenario():
    repo = _FakeBatchRepo()
    service = EvaluationBatchService(batch_repo=repo)
    batch = service.create_batch(
        submitted_by_user_id="user-1",
        agent_user_id="agent-1",
        scenario_ids=["scenario-1"],
        sandbox="local",
        max_concurrent=1,
    )

    updated = service.record_eval_error(batch["batch_id"], "scenario-1", RuntimeError("boom"))

    assert updated["status"] == "failed"
    assert updated["finished_at"]
    assert updated["summary_json"] == {"error": "boom"}


def test_batch_service_returns_batch_detail_with_runs():
    repo = _FakeBatchRepo()
    service = EvaluationBatchService(batch_repo=repo)
    batch = service.create_batch(
        submitted_by_user_id="user-1",
        agent_user_id="agent-1",
        scenario_ids=["scenario-1", "scenario-2"],
        sandbox="local",
        max_concurrent=1,
    )

    detail = service.get_batch_detail(batch["batch_id"])

    assert detail["batch"]["batch_id"] == batch["batch_id"]
    assert [row["scenario_id"] for row in detail["runs"]] == ["scenario-1", "scenario-2"]


def test_batch_service_finds_batch_run_by_eval_run_id():
    repo = _FakeBatchRepo()
    service = EvaluationBatchService(batch_repo=repo)
    batch = service.create_batch(
        submitted_by_user_id="user-1",
        agent_user_id="agent-1",
        scenario_ids=["scenario-1"],
        sandbox="local",
        max_concurrent=1,
    )
    batch_run = repo.list_batch_runs(batch["batch_id"])[0]
    repo.update_batch_run(batch_run["batch_run_id"], eval_run_id="eval-run-1", thread_id="thread-1")

    found = service.get_batch_run_for_eval_run("eval-run-1")

    assert found is not None
    assert found["batch_id"] == batch["batch_id"]
    assert found["thread_id"] == "thread-1"
