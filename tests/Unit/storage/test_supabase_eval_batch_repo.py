from storage.providers.supabase.eval_batch_repo import SupabaseEvaluationBatchRepo


class _FakeExec:
    def __init__(self, rows):
        self.data = rows


class _FakeQuery:
    def __init__(self, table):
        self._table = table
        self._filters: list[tuple[str, object]] = []
        self._insert_payload = None
        self._update_payload = None
        self._limit = None

    def select(self, *_args, **_kwargs):
        return self

    def insert(self, payload):
        self._insert_payload = payload
        return self

    def update(self, payload):
        self._update_payload = payload
        return self

    def eq(self, key, value):
        self._filters.append((key, value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, value):
        self._limit = value
        return self

    def execute(self):
        if self._insert_payload is not None:
            payloads = self._insert_payload if isinstance(self._insert_payload, list) else [self._insert_payload]
            self._table.rows.extend(dict(payload) for payload in payloads)
            return _FakeExec([dict(payload) for payload in payloads])
        rows = [row for row in self._table.rows if all(row.get(key) == value for key, value in self._filters)]
        if self._update_payload is not None:
            for row in rows:
                row.update(self._update_payload)
            return _FakeExec([dict(row) for row in rows])
        if self._limit is not None:
            rows = rows[: self._limit]
        return _FakeExec([dict(row) for row in rows])


class _FakeTable:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *args, **kwargs):
        return _FakeQuery(self).select(*args, **kwargs)

    def insert(self, payload):
        return _FakeQuery(self).insert(payload)

    def update(self, payload):
        return _FakeQuery(self).update(payload)


class _FakeClient:
    def __init__(self):
        self.tables = {
            "evaluation_batches": _FakeTable(
                [
                    {
                        "batch_id": "batch-1",
                        "kind": "scenario_batch",
                        "submitted_by_user_id": "user-1",
                        "agent_user_id": "agent-1",
                        "config_json": {"sandbox": "local"},
                        "status": "pending",
                        "created_at": "2026-04-11T00:00:00Z",
                        "updated_at": "2026-04-11T00:00:00Z",
                        "summary_json": {"total_runs": 1},
                    }
                ]
            ),
            "evaluation_batch_runs": _FakeTable([]),
        }

    def table(self, _name):
        return self.tables[_name]


def test_supabase_eval_batch_repo_maps_batch_rows():
    repo = SupabaseEvaluationBatchRepo(_FakeClient())

    row = repo.get_batch("batch-1")
    assert row["batch_id"] == "batch-1"


def test_supabase_eval_batch_repo_creates_and_lists_batches():
    repo = SupabaseEvaluationBatchRepo(_FakeClient())

    repo.create_batch(
        {
            "batch_id": "batch-2",
            "kind": "scenario_batch",
            "submitted_by_user_id": "user-1",
            "agent_user_id": "agent-1",
            "config_json": {"sandbox": "daytona_selfhost"},
            "status": "pending",
            "created_at": "2026-04-11T00:01:00Z",
            "updated_at": "2026-04-11T00:01:00Z",
            "summary_json": {"total_runs": 2},
        }
    )

    rows = repo.list_batches()
    assert [row["batch_id"] for row in rows] == ["batch-1", "batch-2"]


def test_supabase_eval_batch_repo_updates_batch_summary():
    repo = SupabaseEvaluationBatchRepo(_FakeClient())

    row = repo.update_batch("batch-1", status="running", summary_json={"running_runs": 1})

    assert row is not None
    assert row["status"] == "running"
    assert row["summary_json"]["running_runs"] == 1


def test_supabase_eval_batch_repo_creates_lists_and_updates_batch_runs():
    repo = SupabaseEvaluationBatchRepo(_FakeClient())

    created = repo.create_batch_run(
        {
            "batch_run_id": "batch-run-1",
            "batch_id": "batch-1",
            "item_key": "s1",
            "scenario_id": "scenario-1",
            "status": "pending",
            "thread_id": None,
            "eval_run_id": None,
            "started_at": None,
            "finished_at": None,
            "summary_json": {},
        }
    )
    updated = repo.update_batch_run(
        created["batch_run_id"],
        status="completed",
        thread_id="thread-1",
        eval_run_id="eval-run-1",
        summary_json={"tool_calls": 2},
    )
    rows = repo.list_batch_runs("batch-1")

    assert updated is not None
    assert updated["status"] == "completed"
    assert updated["eval_run_id"] == "eval-run-1"
    assert rows[0]["summary_json"]["tool_calls"] == 2


def test_supabase_eval_batch_repo_finds_batch_run_by_eval_run_id():
    repo = SupabaseEvaluationBatchRepo(_FakeClient())
    created = repo.create_batch_run(
        {
            "batch_run_id": "batch-run-1",
            "batch_id": "batch-1",
            "item_key": "s1",
            "scenario_id": "scenario-1",
            "status": "completed",
            "thread_id": "thread-1",
            "eval_run_id": "eval-run-1",
            "started_at": None,
            "finished_at": None,
            "summary_json": {},
        }
    )

    found = repo.get_batch_run_by_eval_run_id("eval-run-1")

    assert found == created
    assert repo.get_batch_run_by_eval_run_id("missing-run") is None


def test_supabase_eval_batch_repo_lists_batch_runs_by_thread_id():
    repo = SupabaseEvaluationBatchRepo(_FakeClient())
    first = repo.create_batch_run(
        {
            "batch_run_id": "batch-run-1",
            "batch_id": "batch-1",
            "item_key": "s1",
            "scenario_id": "scenario-1",
            "status": "completed",
            "thread_id": "thread-1",
            "eval_run_id": "eval-run-1",
            "started_at": None,
            "finished_at": None,
            "summary_json": {},
        }
    )
    repo.create_batch_run(
        {
            "batch_run_id": "batch-run-2",
            "batch_id": "batch-1",
            "item_key": "s2",
            "scenario_id": "scenario-2",
            "status": "completed",
            "thread_id": "thread-2",
            "eval_run_id": "eval-run-2",
            "started_at": None,
            "finished_at": None,
            "summary_json": {},
        }
    )

    assert repo.list_batch_runs_by_thread_id("thread-1") == [first]
    assert repo.list_batch_runs_by_thread_id("missing-thread") == []
