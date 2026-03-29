"""Tests for scheduled task panel API."""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_client(monkeypatch, tmp_path):
    from backend.scheduled_tasks import runtime, service
    from backend.web.routers import panel

    db_path = tmp_path / "scheduled-api.db"
    monkeypatch.setattr(service, "DB_PATH", db_path)

    class FakeScheduler:
        def __init__(self):
            self.calls: list[str] = []

        async def trigger_task(self, scheduled_task_id: str):
            self.calls.append(scheduled_task_id)
            return runtime.service.create_scheduled_task_run(
                scheduled_task_id=scheduled_task_id,
                thread_id="thread-from-trigger",
                status="dispatched",
                dispatch_result={"status": "started", "run_id": "run-from-api"},
                thread_run_id="run-from-api",
            )

    app = FastAPI()
    app.state.scheduled_task_scheduler = FakeScheduler()
    app.include_router(panel.router)
    return TestClient(app), service


def test_create_list_update_delete_scheduled_task(monkeypatch, tmp_path):
    client, service = _make_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/panel/scheduled-tasks",
        json={
            "thread_id": "thread-1",
            "name": "Morning Brief",
            "instruction": "Summarize overnight activity.",
            "cron_expression": "0 9 * * *",
            "enabled": True,
        },
    )
    assert response.status_code == 200
    item = response.json()["item"]
    assert item["thread_id"] == "thread-1"
    assert item["enabled"] == 1

    response = client.get("/api/panel/scheduled-tasks")
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["items"]] == [item["id"]]

    response = client.put(
        f"/api/panel/scheduled-tasks/{item['id']}",
        json={"name": "Renamed Brief", "enabled": False},
    )
    assert response.status_code == 200
    updated = response.json()["item"]
    assert updated["name"] == "Renamed Brief"
    assert updated["enabled"] == 0

    response = client.delete(f"/api/panel/scheduled-tasks/{item['id']}")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert service.get_scheduled_task(item["id"]) is None


def test_trigger_and_list_runs(monkeypatch, tmp_path):
    client, service = _make_client(monkeypatch, tmp_path)

    task = service.create_scheduled_task(
        thread_id="thread-2",
        name="Review",
        instruction="Review open failures.",
        cron_expression="*/10 * * * *",
    )

    response = client.post(f"/api/panel/scheduled-tasks/{task['id']}/run")
    assert response.status_code == 200
    run = response.json()["item"]
    assert run["scheduled_task_id"] == task["id"]
    assert run["status"] == "dispatched"

    response = client.get(f"/api/panel/scheduled-tasks/{task['id']}/runs")
    assert response.status_code == 200
    runs = response.json()["items"]
    assert [row["id"] for row in runs] == [run["id"]]


def test_trigger_missing_scheduled_task_returns_404(monkeypatch, tmp_path):
    client, _service = _make_client(monkeypatch, tmp_path)

    class MissingScheduler:
        async def trigger_task(self, scheduled_task_id: str):
            raise ValueError(f"Scheduled task not found: {scheduled_task_id}")

    client.app.state.scheduled_task_scheduler = MissingScheduler()

    response = client.post("/api/panel/scheduled-tasks/missing/run")
    assert response.status_code == 404
    assert response.json()["detail"] == "Scheduled task not found"
