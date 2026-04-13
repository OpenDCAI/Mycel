from __future__ import annotations

import pytest

from storage.providers.supabase.schedule_repo import SupabaseScheduleRepo
from tests.fakes.supabase import FakeSupabaseClient


def test_schedule_repo_uses_agent_tables_under_staging_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    tables: dict[str, list[dict]] = {}
    repo = SupabaseScheduleRepo(FakeSupabaseClient(tables))

    created = repo.create(
        owner_user_id="owner_1",
        agent_user_id="agent_1",
        cron_expression="*/15 * * * *",
        instruction_template="Summarize project state",
        create_thread_on_run=True,
    )

    assert created["owner_user_id"] == "owner_1"
    assert created["agent_user_id"] == "agent_1"
    assert tables["agent.schedules"][0]["agent_user_id"] == "agent_1"
    assert "cron_jobs" not in tables


def test_schedule_repo_manages_runs_under_agent_schedule_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    tables: dict[str, list[dict]] = {}
    repo = SupabaseScheduleRepo(FakeSupabaseClient(tables))

    run = repo.create_run(
        schedule_id="schedule_1",
        owner_user_id="owner_1",
        agent_user_id="agent_1",
        triggered_by="manual",
        input_json={"source": "test"},
    )
    updated = repo.update_run(run["id"], status="running", thread_id="thread_1")

    assert tables["agent.schedule_runs"][0]["schedule_id"] == "schedule_1"
    assert repo.list_runs("schedule_1")[0]["input_json"] == {"source": "test"}
    assert updated is not None
    assert updated["status"] == "running"
    assert updated["thread_id"] == "thread_1"


def test_schedule_repo_rejects_public_runtime_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "public")

    with pytest.raises(RuntimeError, match="no route"):
        SupabaseScheduleRepo(FakeSupabaseClient()).list_by_owner("owner_1")
