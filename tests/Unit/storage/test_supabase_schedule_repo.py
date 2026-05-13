from __future__ import annotations

from storage.providers.supabase.schedule_repo import SupabaseScheduleRepo
from tests.fakes.supabase import FakeSupabaseClient


def test_schedule_repo_writes_schedules_to_agent_schema() -> None:
    tables: dict[str, list[dict]] = {}
    repo = SupabaseScheduleRepo(FakeSupabaseClient(tables))

    created = repo.create(
        owner_user_id="owner-1",
        agent_user_id="agent-1",
        cron_expression="*/15 * * * *",
        instruction_template="Summarize project state",
        create_thread_on_run=True,
    )

    assert created["owner_user_id"] == "owner-1"
    assert tables["agent.schedules"][0]["agent_user_id"] == "agent-1"
    assert "staging.schedules" not in tables
    assert "public.schedules" not in tables
    assert "cron_jobs" not in tables


def test_schedule_repo_manages_runs_under_agent_schedule_runs() -> None:
    tables: dict[str, list[dict]] = {}
    repo = SupabaseScheduleRepo(FakeSupabaseClient(tables))

    run = repo.create_run(
        schedule_id="schedule-1",
        owner_user_id="owner-1",
        agent_user_id="agent-1",
        triggered_by="manual",
        input_json={"source": "unit-test"},
    )
    updated = repo.update_run(run["id"], status="running", thread_id="thread-1")

    assert tables["agent.schedule_runs"][0]["schedule_id"] == "schedule-1"
    assert repo.list_runs("schedule-1")[0]["input_json"] == {"source": "unit-test"}
    assert updated is not None
    assert updated["status"] == "running"
    assert updated["thread_id"] == "thread-1"
