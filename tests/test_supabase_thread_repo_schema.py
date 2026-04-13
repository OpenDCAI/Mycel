from __future__ import annotations

import pytest

from storage.providers.supabase.thread_repo import SupabaseThreadRepo
from tests.fakes.supabase import FakeSupabaseClient


def test_thread_repo_lists_staging_threads_by_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    client = FakeSupabaseClient(
        tables={
            "users": [
                {
                    "id": "agent_1",
                    "owner_user_id": "owner_1",
                    "display_name": "Builder",
                    "avatar": "avatar.png",
                }
            ],
            "threads": [
                {
                    "id": "thread_1",
                    "agent_user_id": "agent_1",
                    "sandbox_type": "local",
                    "model": "large",
                    "cwd": "/work",
                    "is_main": 1,
                    "branch_index": 0,
                    "created_at": 1.0,
                }
            ],
        }
    )

    rows = SupabaseThreadRepo(client).list_by_owner_user_id("owner_1")

    assert rows == [
        {
            "id": "thread_1",
            "member_id": "agent_1",
            "sandbox_type": "local",
            "model": "large",
            "cwd": "/work",
            "observation_provider": None,
            "is_main": True,
            "branch_index": 0,
            "created_at": 1.0,
            "member_name": "Builder",
            "member_avatar": "avatar.png",
            "entity_name": None,
        }
    ]


def test_thread_repo_rejects_unknown_runtime_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "identity")

    with pytest.raises(RuntimeError):
        SupabaseThreadRepo(FakeSupabaseClient()).list_by_owner_user_id("owner_1")
