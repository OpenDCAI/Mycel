from storage.providers.supabase.tool_task_repo import SupabaseToolTaskRepo


class _FakeTable:
    def __init__(self, rows):
        self.rows = rows
        self.eq_calls: list[tuple[str, object]] = []

    def select(self, _cols, count=None):
        return self

    def eq(self, key, value):
        self.eq_calls.append((key, value))
        return self

    def execute(self):
        return type("Resp", (), {"data": self.rows})()


class _FakeClient:
    def __init__(self, rows):
        self.table_obj = _FakeTable(rows)
        self.table_names: list[str] = []

    def table(self, name):
        self.table_names.append(name)
        return self.table_obj


def test_supabase_tool_task_repo_next_id_uses_max_existing_id_not_row_count():
    client = _FakeClient(
        [
            {"task_id": "1"},
            {"task_id": "3"},
        ]
    )
    repo = SupabaseToolTaskRepo(client)

    assert repo.next_id("thread-gap") == "4"


def test_supabase_tool_task_repo_uses_agent_thread_tasks_table():
    client = _FakeClient([])
    repo = SupabaseToolTaskRepo(client)

    repo.next_id("thread-empty")

    assert client.table_names == ["agent_thread_tasks"]
