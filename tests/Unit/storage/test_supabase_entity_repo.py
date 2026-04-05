from storage.providers.supabase.entity_repo import SupabaseEntityRepo
from tests.fakes.supabase import FakeSupabaseClient


def test_supabase_entity_repo_get_by_thread_id_returns_matching_entity():
    tables = {
        "entities": [
            {
                "id": "entity-1",
                "type": "agent",
                "member_id": "member-1",
                "name": "worker-1",
                "avatar": None,
                "thread_id": "thread-1",
                "created_at": 1.0,
            }
        ]
    }
    repo = SupabaseEntityRepo(FakeSupabaseClient(tables))

    row = repo.get_by_thread_id("thread-1")

    assert row is not None
    assert row.id == "entity-1"
    assert row.thread_id == "thread-1"


def test_supabase_entity_repo_get_by_thread_id_returns_none_when_missing():
    repo = SupabaseEntityRepo(FakeSupabaseClient({"entities": []}))

    assert repo.get_by_thread_id("thread-missing") is None
