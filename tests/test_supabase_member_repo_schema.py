from __future__ import annotations

import pytest

from storage.contracts import MemberType
from storage.providers.supabase.member_repo import SupabaseMemberRepo
from tests.fakes.supabase import FakeSupabaseClient


def test_member_repo_uses_staging_users_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    client = FakeSupabaseClient(
        tables={
            "users": [
                {
                    "id": "u_1",
                    "type": "human",
                    "display_name": "Ada",
                    "avatar": "avatar.png",
                    "bio": "operator",
                    "owner_user_id": None,
                    "next_thread_seq": 7,
                    "created_at": 1.0,
                    "updated_at": 2.0,
                    "email": "ada@example.test",
                    "mycel_id": 42,
                }
            ],
        }
    )

    row = SupabaseMemberRepo(client).get_by_id("u_1")

    assert row is not None
    assert row.id == "u_1"
    assert row.name == "Ada"
    assert row.type is MemberType.HUMAN
    assert row.description == "operator"
    assert row.next_entity_seq == 7


def test_member_repo_maps_staging_agent_type(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    client = FakeSupabaseClient(
        tables={
            "users": [
                {
                    "id": "agent_1",
                    "type": "agent",
                    "display_name": "Builder",
                    "created_at": 1.0,
                    "next_thread_seq": 0,
                }
            ],
        }
    )

    row = SupabaseMemberRepo(client).get_by_id("agent_1")

    assert row is not None
    assert row.type is MemberType.MYCEL_AGENT


def test_member_repo_rejects_unknown_runtime_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "identity")

    with pytest.raises(RuntimeError):
        SupabaseMemberRepo(FakeSupabaseClient()).get_by_id("u_1")
