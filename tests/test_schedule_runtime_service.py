from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.web.services import schedule_runtime_service


class FakeThreadRepo:
    def __init__(self, rows: dict[str, dict]) -> None:
        self._rows = rows

    def get_by_id(self, thread_id: str) -> dict | None:
        return self._rows.get(thread_id)


class FakeScheduleStore:
    def __init__(self, schedule: dict) -> None:
        self.schedule = schedule
        self.runs: list[dict] = []
        self.updated_runs: list[tuple[str, dict]] = []
        self.updated_schedules: list[tuple[str, dict]] = []

    def get_schedule(self, schedule_id: str) -> dict | None:
        return self.schedule if self.schedule["id"] == schedule_id else None

    def create_schedule_run(self, **fields) -> dict:
        run = {"id": "run_1", "status": "queued", **fields}
        self.runs.append(run)
        return run

    def update_schedule_run(self, run_id: str, **fields) -> dict | None:
        self.updated_runs.append((run_id, fields))
        run = next((item for item in self.runs if item["id"] == run_id), None)
        if run is None:
            return None
        run.update(fields)
        return run

    def update_schedule(self, schedule_id: str, **fields) -> dict | None:
        self.updated_schedules.append((schedule_id, fields))
        self.schedule.update(fields)
        return self.schedule


@pytest.mark.asyncio
async def test_trigger_schedule_routes_target_thread_and_marks_run_running(monkeypatch: pytest.MonkeyPatch) -> None:
    store = FakeScheduleStore(
        {
            "id": "schedule_1",
            "owner_user_id": "owner_1",
            "agent_user_id": "agent_1",
            "target_thread_id": "thread_1",
            "create_thread_on_run": False,
            "enabled": True,
            "instruction_template": "Summarize today.",
        }
    )
    app = SimpleNamespace(
        state=SimpleNamespace(thread_repo=FakeThreadRepo({"thread_1": {"owner_user_id": "owner_1", "member_id": "agent_1"}}))
    )
    routed: dict[str, str] = {}

    async def fake_route_message_to_brain(_app, thread_id: str, content: str, source: str):
        routed.update({"thread_id": thread_id, "content": content, "source": source})
        return {"status": "started", "routing": "direct", "run_id": "agent_run_1", "thread_id": thread_id}

    monkeypatch.setattr(schedule_runtime_service.schedule_service, "get_schedule", store.get_schedule)
    monkeypatch.setattr(schedule_runtime_service.schedule_service, "create_schedule_run", store.create_schedule_run)
    monkeypatch.setattr(schedule_runtime_service.schedule_service, "update_schedule_run", store.update_schedule_run)
    monkeypatch.setattr(schedule_runtime_service.schedule_service, "update_schedule", store.update_schedule)
    monkeypatch.setattr(schedule_runtime_service, "route_message_to_brain", fake_route_message_to_brain)

    result = await schedule_runtime_service.trigger_schedule(app, "schedule_1", owner_user_id="owner_1")

    assert routed["thread_id"] == "thread_1"
    assert routed["source"] == "schedule"
    assert "Schedule ID: schedule_1" in routed["content"]
    assert "Schedule Run ID: run_1" in routed["content"]
    assert "Summarize today." in routed["content"]
    assert result["schedule_run"]["status"] == "running"
    assert result["routing"]["status"] == "started"
    assert store.runs[0]["status"] == "running"
    assert store.updated_runs[-1][1]["status"] == "running"
    assert store.updated_runs[-1][1]["thread_id"] == "thread_1"
    assert store.updated_schedules[-1][0] == "schedule_1"
    assert "last_run_at" in store.updated_schedules[-1][1]


@pytest.mark.asyncio
async def test_trigger_schedule_rejects_create_thread_on_run_without_target(monkeypatch: pytest.MonkeyPatch) -> None:
    store = FakeScheduleStore(
        {
            "id": "schedule_1",
            "owner_user_id": "owner_1",
            "agent_user_id": "agent_1",
            "target_thread_id": None,
            "create_thread_on_run": True,
            "enabled": True,
            "instruction_template": "Work.",
        }
    )
    app = SimpleNamespace(state=SimpleNamespace(thread_repo=FakeThreadRepo({})))
    route_called = False

    async def fake_route_message_to_brain(*_args, **_kwargs):
        nonlocal route_called
        route_called = True
        return {}

    monkeypatch.setattr(schedule_runtime_service.schedule_service, "get_schedule", store.get_schedule)
    monkeypatch.setattr(schedule_runtime_service, "route_message_to_brain", fake_route_message_to_brain)

    with pytest.raises(ValueError, match="target_thread_id"):
        await schedule_runtime_service.trigger_schedule(app, "schedule_1", owner_user_id="owner_1")

    assert route_called is False
    assert store.runs == []


@pytest.mark.asyncio
async def test_trigger_schedule_marks_run_failed_when_routing_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    store = FakeScheduleStore(
        {
            "id": "schedule_1",
            "owner_user_id": "owner_1",
            "agent_user_id": "agent_1",
            "target_thread_id": "thread_1",
            "create_thread_on_run": False,
            "enabled": True,
            "instruction_template": "Work.",
        }
    )
    app = SimpleNamespace(
        state=SimpleNamespace(thread_repo=FakeThreadRepo({"thread_1": {"owner_user_id": "owner_1", "member_id": "agent_1"}}))
    )

    async def fake_route_message_to_brain(*_args, **_kwargs):
        raise RuntimeError("route failed")

    monkeypatch.setattr(schedule_runtime_service.schedule_service, "get_schedule", store.get_schedule)
    monkeypatch.setattr(schedule_runtime_service.schedule_service, "create_schedule_run", store.create_schedule_run)
    monkeypatch.setattr(schedule_runtime_service.schedule_service, "update_schedule_run", store.update_schedule_run)
    monkeypatch.setattr(schedule_runtime_service, "route_message_to_brain", fake_route_message_to_brain)

    with pytest.raises(RuntimeError, match="route failed"):
        await schedule_runtime_service.trigger_schedule(app, "schedule_1", owner_user_id="owner_1")

    assert store.updated_runs[-1][1]["status"] == "failed"
    assert store.updated_runs[-1][1]["error"] == "route failed"
    assert "completed_at" in store.updated_runs[-1][1]
