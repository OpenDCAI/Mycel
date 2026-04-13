from __future__ import annotations

import pytest

from backend.web.services import schedule_service


class FakeScheduleRepo:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.runs: list[dict] = []

    def close(self) -> None:
        return None

    def list_by_owner(self, owner_user_id: str) -> list[dict]:
        return [row for row in self.created if row["owner_user_id"] == owner_user_id]

    def get(self, schedule_id: str) -> dict | None:
        return next((row for row in self.created if row["id"] == schedule_id), None)

    def create(self, **fields):
        row = {"id": "schedule_1", **fields}
        self.created.append(row)
        return row

    def update(self, schedule_id: str, **fields):
        row = self.get(schedule_id)
        if row is None:
            return None
        row.update(fields)
        return row

    def delete(self, schedule_id: str) -> bool:
        before = len(self.created)
        self.created = [row for row in self.created if row["id"] != schedule_id]
        return len(self.created) < before

    def create_run(self, **fields):
        row = {"id": "run_1", **fields}
        self.runs.append(row)
        return row

    def list_runs(self, schedule_id: str) -> list[dict]:
        return [row for row in self.runs if row["schedule_id"] == schedule_id]

    def update_run(self, run_id: str, **fields):
        row = next((item for item in self.runs if item["id"] == run_id), None)
        if row is None:
            return None
        row.update(fields)
        return row


def test_schedule_service_requires_target_thread_or_create_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_service, "make_schedule_repo", lambda: FakeScheduleRepo())

    with pytest.raises(ValueError, match="target"):
        schedule_service.create_schedule(
            owner_user_id="owner_1",
            agent_user_id="agent_1",
            cron_expression="*/15 * * * *",
            instruction_template="work",
        )


def test_schedule_service_creates_valid_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FakeScheduleRepo()
    monkeypatch.setattr(schedule_service, "make_schedule_repo", lambda: repo)

    created = schedule_service.create_schedule(
        owner_user_id="owner_1",
        agent_user_id="agent_1",
        cron_expression="*/15 * * * *",
        instruction_template="work",
        create_thread_on_run=True,
    )

    assert created["id"] == "schedule_1"
    assert repo.created[0]["owner_user_id"] == "owner_1"


def test_schedule_service_validates_run_trigger_and_status(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FakeScheduleRepo()
    monkeypatch.setattr(schedule_service, "make_schedule_repo", lambda: repo)

    with pytest.raises(ValueError, match="triggered_by"):
        schedule_service.create_schedule_run(
            schedule_id="schedule_1",
            owner_user_id="owner_1",
            agent_user_id="agent_1",
            triggered_by="button",
        )

    run = schedule_service.create_schedule_run(
        schedule_id="schedule_1",
        owner_user_id="owner_1",
        agent_user_id="agent_1",
        triggered_by="manual",
    )

    with pytest.raises(ValueError, match="status"):
        schedule_service.update_schedule_run(run["id"], status="done")
