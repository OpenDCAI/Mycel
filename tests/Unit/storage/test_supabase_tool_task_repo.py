from core.tools.task.types import Task, TaskStatus
from storage.providers.supabase.tool_task_repo import SupabaseToolTaskRepo
from tests.fakes.supabase import FakeSupabaseClient


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

    def schema(self, name):
        self.table_names.append(f"schema:{name}")
        return self

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


def test_supabase_tool_task_repo_uses_agent_schema_thread_tasks_table():
    client = _FakeClient([])
    repo = SupabaseToolTaskRepo(client)

    repo.next_id("thread-empty")

    assert client.table_names == ["schema:agent", "thread_tasks"]


def test_supabase_tool_task_repo_reads_agent_thread_tasks_schema_table() -> None:
    client = FakeSupabaseClient(
        tables={
            "agent.thread_tasks": [
                {
                    "thread_id": "thread-1",
                    "task_id": "1",
                    "subject": "Route runtime",
                    "description": "Read from target domain table",
                    "status": "pending",
                    "active_form": None,
                    "owner": None,
                    "blocks": [],
                    "blocked_by": [],
                    "metadata": {},
                }
            ]
        }
    )
    repo = SupabaseToolTaskRepo(client)

    assert repo.list_all("thread-1") == [
        Task(
            id="1",
            subject="Route runtime",
            description="Read from target domain table",
            status=TaskStatus.PENDING,
        )
    ]
