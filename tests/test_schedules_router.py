from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.web.core.dependencies import get_current_user_id
from backend.web.routers import schedules


def test_run_schedule_endpoint_calls_runtime_with_authenticated_user(monkeypatch) -> None:
    app = FastAPI()
    app.state.marker = "app-state"
    app.include_router(schedules.router)
    app.dependency_overrides[get_current_user_id] = lambda: "owner_1"
    calls: list[dict] = []

    async def fake_trigger_schedule(app_obj, schedule_id: str, *, owner_user_id: str, triggered_by: str):
        calls.append(
            {
                "app_marker": app_obj.state.marker,
                "schedule_id": schedule_id,
                "owner_user_id": owner_user_id,
                "triggered_by": triggered_by,
            }
        )
        return {"schedule_run": {"id": "run_1", "status": "running"}, "routing": {"status": "started"}}

    monkeypatch.setattr(schedules.schedule_runtime_service, "trigger_schedule", fake_trigger_schedule)

    response = TestClient(app).post("/api/schedules/schedule_1/run")

    assert response.status_code == 200
    assert response.json()["item"]["schedule_run"]["id"] == "run_1"
    assert calls == [
        {
            "app_marker": "app-state",
            "schedule_id": "schedule_1",
            "owner_user_id": "owner_1",
            "triggered_by": "manual",
        }
    ]
