from __future__ import annotations

from storage.providers.supabase.queue_repo import SupabaseQueueRepo
from tests.fakes.supabase import FakeSupabaseClient


def test_supabase_queue_repo_enqueue_persists_sender_user_id() -> None:
    tables = {"message_queue": []}
    repo = SupabaseQueueRepo(client=FakeSupabaseClient(tables=tables))

    repo.enqueue(
        "thread-1",
        "hello",
        notification_type="steer",
        source="owner",
        sender_id="user-1",
        sender_name="Alice",
    )

    row = tables["message_queue"][0]
    assert row["thread_id"] == "thread-1"
    assert row["sender_user_id"] == "user-1"
    assert "sender_id" not in row


def test_supabase_queue_repo_dequeue_maps_sender_user_id_to_sender_id() -> None:
    tables = {
        "message_queue": [
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
    assert tables["message_queue"] == []


def test_supabase_queue_repo_drain_all_maps_sender_user_id_to_sender_id() -> None:
    tables = {
        "message_queue": [
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
    assert tables["message_queue"] == []
