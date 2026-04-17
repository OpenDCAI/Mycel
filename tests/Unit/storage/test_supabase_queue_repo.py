from __future__ import annotations

from storage.providers.supabase.queue_repo import SupabaseQueueRepo
from tests.fakes.supabase import FakeSupabaseClient


class _RecordingSupabaseClient(FakeSupabaseClient):
    def __init__(self, tables: dict):
        super().__init__(tables=tables)
        self.table_names: list[str] = []

    def table(self, table_name: str):
        resolved_table = f"{self._schema_name}.{table_name}" if self._schema_name else table_name
        self.table_names.append(resolved_table)
        return super().table(table_name)

    def schema(self, schema_name: str):
        scoped = _RecordingSupabaseClient(self._tables)
        scoped._schema_name = schema_name
        scoped.table_names = self.table_names
        return scoped


def test_supabase_queue_repo_enqueue_persists_sender_user_id() -> None:
    tables = {"agent.message_queue": []}
    repo = SupabaseQueueRepo(client=FakeSupabaseClient(tables=tables))

    repo.enqueue(
        "thread-1",
        "hello",
        notification_type="steer",
        source="owner",
        sender_id="user-1",
        sender_name="Alice",
    )

    row = tables["agent.message_queue"][0]
    assert row["thread_id"] == "thread-1"
    assert row["sender_user_id"] == "user-1"
    assert "sender_id" not in row


def test_supabase_queue_repo_dequeue_maps_sender_user_id_to_sender_id() -> None:
    tables = {
        "agent.message_queue": [
            {
                "id": 1,
                "thread_id": "thread-1",
                "content": "hello",
                "notification_type": "steer",
                "source": "owner",
                "sender_user_id": "user-1",
                "sender_name": "Alice",
            }
        ]
    }
    repo = SupabaseQueueRepo(client=FakeSupabaseClient(tables=tables))

    item = repo.dequeue("thread-1")

    assert item is not None
    assert item.sender_id == "user-1"
    assert tables["agent.message_queue"] == []


def test_supabase_queue_repo_drain_all_maps_sender_user_id_to_sender_id() -> None:
    tables = {
        "agent.message_queue": [
            {
                "id": 1,
                "thread_id": "thread-1",
                "content": "hello",
                "notification_type": "steer",
                "source": "owner",
                "sender_user_id": "user-1",
                "sender_name": "Alice",
            },
            {
                "id": 2,
                "thread_id": "thread-1",
                "content": "world",
                "notification_type": "agent",
                "source": "external",
                "sender_user_id": "user-2",
                "sender_name": "Bob",
            },
        ]
    }
    repo = SupabaseQueueRepo(client=FakeSupabaseClient(tables=tables))

    items = repo.drain_all("thread-1")

    assert [item.sender_id for item in items] == ["user-1", "user-2"]
    assert tables["agent.message_queue"] == []


def test_supabase_queue_repo_uses_agent_schema_table() -> None:
    client = _RecordingSupabaseClient({"agent.message_queue": []})
    repo = SupabaseQueueRepo(client=client)

    repo.enqueue("thread-1", "hello")

    assert client.table_names == ["agent.message_queue"]
