from __future__ import annotations

from storage.container import StorageContainer
from storage.runtime import build_schedule_repo, build_storage_container
from tests.fakes.supabase import FakeSupabaseClient


def test_storage_container_exposes_schedule_repo() -> None:
    tables: dict[str, list[dict]] = {}
    container = StorageContainer(supabase_client=FakeSupabaseClient(tables))

    repo = container.schedule_repo()
    repo.create(
        owner_user_id="owner-1",
        agent_user_id="agent-1",
        cron_expression="0 * * * *",
        instruction_template="work",
        create_thread_on_run=True,
    )

    assert tables["agent.schedules"][0]["owner_user_id"] == "owner-1"


def test_build_schedule_repo_uses_runtime_container() -> None:
    tables: dict[str, list[dict]] = {}
    repo = build_schedule_repo(supabase_client=FakeSupabaseClient(tables))

    repo.create_run(
        schedule_id="schedule-1",
        owner_user_id="owner-1",
        agent_user_id="agent-1",
        triggered_by="manual",
    )

    assert tables["agent.schedule_runs"][0]["triggered_by"] == "manual"


def test_build_storage_container_exposes_schedule_repo() -> None:
    container = build_storage_container(supabase_client=FakeSupabaseClient())

    assert container.schedule_repo().__class__.__name__ == "SupabaseScheduleRepo"
