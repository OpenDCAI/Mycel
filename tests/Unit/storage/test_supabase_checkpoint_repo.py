from storage.providers.supabase.checkpoint_repo import SupabaseCheckpointRepo


class _FakeTable:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.eq_calls: list[tuple[str, object]] = []
        self.delete_calls = 0

    def select(self, _cols):
        return self

    def delete(self):
        self.delete_calls += 1
        return self

    def eq(self, key, value):
        self.eq_calls.append((key, value))
        return self

    def execute(self):
        return type("Resp", (), {"data": self.rows})()


class _FakeClient:
    def __init__(self, rows=None):
        self.table_obj = _FakeTable(rows)
        self.table_names: list[str] = []

    def schema(self, name):
        self.table_names.append(f"schema:{name}")
        return self

    def table(self, name):
        self.table_names.append(name)
        return self.table_obj


def test_supabase_checkpoint_repo_reads_agent_schema_checkpoints_table() -> None:
    client = _FakeClient([{"thread_id": "thread-2"}, {"thread_id": "thread-1"}, {"thread_id": "thread-1"}])
    repo = SupabaseCheckpointRepo(client)

    thread_ids = repo.list_thread_ids()

    assert thread_ids == ["thread-1", "thread-2"]
    assert client.table_names == ["schema:agent", "checkpoints"]


def test_supabase_checkpoint_repo_deletes_agent_schema_checkpoint_family() -> None:
    client = _FakeClient()
    repo = SupabaseCheckpointRepo(client)

    repo.delete_thread_data("thread-1")

    assert client.table_names == [
        "schema:agent",
        "checkpoints",
        "schema:agent",
        "checkpoint_writes",
        "schema:agent",
        "checkpoint_blobs",
    ]
