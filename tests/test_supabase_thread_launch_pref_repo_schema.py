from __future__ import annotations

import pytest

from storage.providers.supabase.thread_launch_pref_repo import SupabaseThreadLaunchPrefRepo
from tests.fakes.supabase import FakeSupabaseClient


def test_thread_launch_pref_repo_reads_staging_agent_user_id_as_member_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    client = FakeSupabaseClient(
        tables={
            "thread_launch_prefs": [
                {
                    "owner_user_id": "owner_1",
                    "agent_user_id": "agent_1",
                    "last_confirmed_json": '{"model":"large"}',
                    "last_successful_json": '{"provider":"local"}',
                    "last_confirmed_at": 1.0,
                    "last_successful_at": 2.0,
                }
            ],
        }
    )

    row = SupabaseThreadLaunchPrefRepo(client).get("owner_1", "agent_1")

    assert row == {
        "owner_user_id": "owner_1",
        "member_id": "agent_1",
        "last_confirmed": {"model": "large"},
        "last_successful": {"provider": "local"},
        "last_confirmed_at": 1.0,
        "last_successful_at": 2.0,
    }


def test_thread_launch_pref_repo_writes_staging_agent_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    tables: dict[str, list[dict]] = {}
    repo = SupabaseThreadLaunchPrefRepo(FakeSupabaseClient(tables=tables))

    repo.save_successful("owner_1", "agent_1", {"model": "large"})

    assert tables["thread_launch_prefs"][0]["owner_user_id"] == "owner_1"
    assert tables["thread_launch_prefs"][0]["agent_user_id"] == "agent_1"
    assert "member_id" not in tables["thread_launch_prefs"][0]


def test_thread_launch_pref_repo_rejects_unknown_runtime_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "identity")

    with pytest.raises(RuntimeError):
        SupabaseThreadLaunchPrefRepo(FakeSupabaseClient()).get("owner_1", "agent_1")
