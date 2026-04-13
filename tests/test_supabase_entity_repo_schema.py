from __future__ import annotations

import pytest

from storage.providers.supabase.entity_repo import SupabaseEntityRepo
from tests.fakes.supabase import FakeSupabaseClient


class NoEntitiesFakeSupabaseClient(FakeSupabaseClient):
    def table(self, table_name: str):
        if table_name == "entities":
            raise AssertionError("SupabaseEntityRepo must not query a missing entities table")
        return super().table(table_name)


def test_entity_repo_derives_human_actor_from_staging_users(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    client = NoEntitiesFakeSupabaseClient(
        tables={
            "users": [
                {
                    "id": "human_1",
                    "type": "human",
                    "display_name": "Ada",
                    "avatar": "avatar.png",
                    "created_at": 1.0,
                    "next_thread_seq": 0,
                }
            ]
        }
    )

    row = SupabaseEntityRepo(client).get_by_id("human_1")

    assert row is not None
    assert row.id == "human_1"
    assert row.type == "human"
    assert row.member_id == "human_1"
    assert row.name == "Ada"
    assert row.avatar == "avatar.png"
    assert row.thread_id is None


def test_entity_repo_derives_agent_actor_with_main_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    client = NoEntitiesFakeSupabaseClient(
        tables={
            "users": [
                {
                    "id": "agent_1",
                    "type": "agent",
                    "display_name": "Builder",
                    "owner_user_id": "human_1",
                    "created_at": 1.0,
                    "next_thread_seq": 0,
                }
            ],
            "agent.threads": [
                {
                    "id": "thread_main",
                    "agent_user_id": "agent_1",
                    "owner_user_id": "human_1",
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

    row = SupabaseEntityRepo(client).get_by_id("agent_1")

    assert row is not None
    assert row.id == "agent_1"
    assert row.type == "agent"
    assert row.member_id == "agent_1"
    assert row.name == "Builder"
    assert row.thread_id == "thread_main"


def test_entity_repo_lists_agent_actors_without_entities_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    client = NoEntitiesFakeSupabaseClient(
        tables={
            "users": [
                {
                    "id": "human_1",
                    "type": "human",
                    "display_name": "Ada",
                    "created_at": 1.0,
                    "next_thread_seq": 0,
                },
                {
                    "id": "agent_1",
                    "type": "agent",
                    "display_name": "Builder",
                    "owner_user_id": "human_1",
                    "created_at": 2.0,
                    "next_thread_seq": 0,
                },
            ],
            "agent.threads": [],
        }
    )

    rows = SupabaseEntityRepo(client).list_by_type("agent")

    assert [(row.id, row.type, row.name, row.thread_id) for row in rows] == [("agent_1", "agent", "Builder", None)]


def test_entity_repo_writes_are_read_model_noops(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    tables = {
        "users": [
            {
                "id": "agent_1",
                "type": "agent",
                "display_name": "Builder",
                "owner_user_id": "human_1",
                "created_at": 1.0,
                "next_thread_seq": 0,
            }
        ],
        "agent.threads": [],
    }
    repo = SupabaseEntityRepo(NoEntitiesFakeSupabaseClient(tables=tables))
    row = repo.get_by_id("agent_1")
    assert row is not None

    repo.create(row)
    repo.update("agent_1", thread_id="thread_main", name="Builder")
    repo.delete("agent_1")

    assert "entities" not in tables
