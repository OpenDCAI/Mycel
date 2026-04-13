from __future__ import annotations

import pytest

from storage.providers.supabase.thread_repo import SupabaseThreadRepo
from tests.fakes.supabase import FakeSupabaseClient


def test_thread_repo_lists_agent_threads_by_owner_under_staging_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    client = FakeSupabaseClient(
        tables={
            "agent.threads": [
                {
                    "id": "thread_1",
                    "agent_user_id": "agent_1",
                    "owner_user_id": "owner_1",
                    "sandbox_type": "local",
                    "model": "large",
                    "cwd": "/work",
                    "is_main": True,
                    "branch_index": 0,
                    "created_at": "2026-04-14T00:00:00+00:00",
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
            "owner_user_id": "owner_1",
            "observation_provider": None,
            "is_main": True,
            "branch_index": 0,
            "created_at": "2026-04-14T00:00:00+00:00",
            "member_name": None,
            "member_avatar": None,
            "entity_name": None,
        }
    ]


def test_thread_repo_get_by_id_exposes_owner_user_id_under_staging_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    client = FakeSupabaseClient(
        tables={
            "agent.threads": [
                {
                    "id": "thread_1",
                    "agent_user_id": "agent_1",
                    "owner_user_id": "owner_1",
                    "sandbox_type": "local",
                    "model": "large",
                    "cwd": "/work",
                    "is_main": True,
                    "branch_index": 0,
                    "created_at": "2026-04-14T00:00:00+00:00",
                }
            ],
        }
    )

    row = SupabaseThreadRepo(client).get_by_id("thread_1")

    assert row is not None
    assert row["owner_user_id"] == "owner_1"
    assert row["member_id"] == "agent_1"


def test_thread_repo_creates_agent_thread_with_owner_and_timestamptz(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    tables: dict[str, list[dict]] = {}
    repo = SupabaseThreadRepo(FakeSupabaseClient(tables=tables))

    repo.create(
        thread_id="thread_1",
        member_id="agent_1",
        sandbox_type="local",
        cwd="/work",
        created_at=1710000000.0,
        owner_user_id="owner_1",
        model="large",
        is_main=True,
        branch_index=0,
    )

    assert tables["agent.threads"] == [
        {
            "id": "thread_1",
            "agent_user_id": "agent_1",
            "owner_user_id": "owner_1",
            "sandbox_type": "local",
            "cwd": "/work",
            "model": "large",
            "is_main": True,
            "branch_index": 0,
            "created_at": "2024-03-09T16:00:00+00:00",
        }
    ]


def test_thread_repo_requires_owner_when_creating_agent_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    repo = SupabaseThreadRepo(FakeSupabaseClient())

    with pytest.raises(ValueError, match="owner_user_id"):
        repo.create(
            thread_id="thread_1",
            member_id="agent_1",
            sandbox_type="local",
            branch_index=0,
            is_main=True,
        )


def test_thread_repo_rejects_unknown_runtime_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "identity")

    with pytest.raises(RuntimeError):
        SupabaseThreadRepo(FakeSupabaseClient()).list_by_owner_user_id("owner_1")
