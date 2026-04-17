from __future__ import annotations

from storage.providers.supabase.run_event_repo import SupabaseRunEventRepo
from tests.fakes.supabase import FakeSupabaseClient


class _RecordingSupabaseClient(FakeSupabaseClient):
    def __init__(self, tables: dict[str, list[dict]], auto_seq_tables: set[str] | None = None):
        super().__init__(tables=tables, auto_seq_tables=auto_seq_tables)
        self.table_names: list[str] = []

    def table(self, table_name: str):
        resolved_table = f"{self._schema_name}.{table_name}" if self._schema_name else table_name
        self.table_names.append(resolved_table)
        return super().table(table_name)

    def schema(self, schema_name: str):
        scoped = _RecordingSupabaseClient(self._tables, auto_seq_tables=self._auto_seq_tables)
        scoped._schema_name = schema_name
        scoped.table_names = self.table_names
        return scoped


def test_supabase_run_event_repo_uses_agent_schema_table() -> None:
    tables: dict[str, list[dict]] = {"agent.run_events": []}
    client = _RecordingSupabaseClient(tables, auto_seq_tables={"agent.run_events"})
    repo = SupabaseRunEventRepo(client)

    seq = repo.append_event(
        "thread-1",
        "run-1",
        "message_delta",
        {"text": "hello"},
        message_id="msg-1",
    )
    events = repo.list_events("thread-1", "run-1")
    latest_seq = repo.latest_seq("thread-1")
    start_seq = repo.run_start_seq("thread-1", "run-1")
    latest_run_id = repo.latest_run_id("thread-1")
    run_ids = repo.list_run_ids("thread-1")
    deleted = repo.delete_runs("thread-1", ["run-1"])

    assert seq == 1
    assert events == [
        {
            "seq": 1,
            "event_type": "message_delta",
            "data": {"text": "hello"},
            "message_id": "msg-1",
        }
    ]
    assert latest_seq == 1
    assert start_seq == 1
    assert latest_run_id == "run-1"
    assert run_ids == ["run-1"]
    assert deleted == 1
    assert tables["agent.run_events"] == []
    assert "run_events" not in tables
    assert client.table_names == [
        "agent.run_events",
        "agent.run_events",
        "agent.run_events",
        "agent.run_events",
        "agent.run_events",
        "agent.run_events",
        "agent.run_events",
        "agent.run_events",
    ]
