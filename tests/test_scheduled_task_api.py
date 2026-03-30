"""Tests for scheduled task panel API."""

from types import SimpleNamespace

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

    class FakeAuthService:
        def verify_token(self, token: str):
            if token == "token-user-1":
                return {"user_id": "user-1", "entity_id": "entity-user-1"}
            if token == "token-user-2":
                return {"user_id": "user-2", "entity_id": "entity-user-2"}
            raise ValueError("Invalid token")

    class FakeMemberRepo:
        def get_by_id(self, member_id: str):
            if member_id == "user-1":
                return SimpleNamespace(id="user-1")
            if member_id == "user-2":
                return SimpleNamespace(id="user-2")
            if member_id == "member-user-1":
                return SimpleNamespace(id="member-user-1", owner_user_id="user-1")
            if member_id == "member-user-2":
                return SimpleNamespace(id="member-user-2", owner_user_id="user-2")
            return None

    class FakeThreadRepo:
        def get_by_id(self, thread_id: str):
            mapping = {
                "thread-1": {"id": "thread-1", "member_id": "member-user-1"},
                "thread-2": {"id": "thread-2", "member_id": "member-user-2"},
                "thread-from-trigger": {"id": "thread-from-trigger", "member_id": "member-user-1"},
            }
            return mapping.get(thread_id)

    app = FastAPI()
    app.state.auth_service = FakeAuthService()
    app.state.member_repo = FakeMemberRepo()
    app.state.thread_repo = FakeThreadRepo()
    app.state.scheduled_task_scheduler = FakeScheduler()
    app.include_router(panel.router)
    return TestClient(app), service


def _auth_headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer token-{user_id}"}


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
        headers=_auth_headers("user-1"),
    )
    assert response.status_code == 200
    item = response.json()["item"]
    assert item["thread_id"] == "thread-1"
    assert item["enabled"] == 1

    response = client.get("/api/panel/scheduled-tasks", headers=_auth_headers("user-1"))
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["items"]] == [item["id"]]

    response = client.put(
        f"/api/panel/scheduled-tasks/{item['id']}",
        json={"name": "Renamed Brief", "enabled": False},
        headers=_auth_headers("user-1"),
    )
    assert response.status_code == 200
    updated = response.json()["item"]
    assert updated["name"] == "Renamed Brief"
    assert updated["enabled"] == 0

    response = client.delete(f"/api/panel/scheduled-tasks/{item['id']}", headers=_auth_headers("user-1"))
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

    response = client.post(f"/api/panel/scheduled-tasks/{task['id']}/run", headers=_auth_headers("user-2"))
    assert response.status_code == 200
    run = response.json()["item"]
    assert run["scheduled_task_id"] == task["id"]
    assert run["status"] == "dispatched"

    response = client.get(f"/api/panel/scheduled-tasks/{task['id']}/runs", headers=_auth_headers("user-2"))
    assert response.status_code == 200
    runs = response.json()["items"]
    assert [row["id"] for row in runs] == [run["id"]]


def test_trigger_missing_scheduled_task_returns_404(monkeypatch, tmp_path):
    client, _service = _make_client(monkeypatch, tmp_path)

    class MissingScheduler:
        async def trigger_task(self, scheduled_task_id: str):
            raise ValueError(f"Scheduled task not found: {scheduled_task_id}")

    client.app.state.scheduled_task_scheduler = MissingScheduler()

    response = client.post("/api/panel/scheduled-tasks/missing/run", headers=_auth_headers("user-1"))
    assert response.status_code == 404
    assert response.json()["detail"] == "Scheduled task not found"


def test_scheduled_tasks_are_scoped_to_current_user(monkeypatch, tmp_path):
    client, service = _make_client(monkeypatch, tmp_path)

    own_task = service.create_scheduled_task(
        thread_id="thread-1",
        name="Own task",
        instruction="Do own work.",
        cron_expression="0 9 * * *",
    )
    other_task = service.create_scheduled_task(
        thread_id="thread-2",
        name="Other task",
        instruction="Do other work.",
        cron_expression="0 10 * * *",
    )

    response = client.get("/api/panel/scheduled-tasks", headers=_auth_headers("user-1"))
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["items"]] == [own_task["id"]]

    response = client.get("/api/panel/scheduled-tasks", headers=_auth_headers("user-2"))
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["items"]] == [other_task["id"]]


def test_cannot_access_other_users_scheduled_task(monkeypatch, tmp_path):
    client, service = _make_client(monkeypatch, tmp_path)

    task = service.create_scheduled_task(
        thread_id="thread-2",
        name="Other task",
        instruction="Do other work.",
        cron_expression="0 10 * * *",
    )

    response = client.get(f"/api/panel/scheduled-tasks/{task['id']}/runs", headers=_auth_headers("user-1"))
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized"

    response = client.put(
        f"/api/panel/scheduled-tasks/{task['id']}",
        json={"name": "Hacked"},
        headers=_auth_headers("user-1"),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized"

    response = client.delete(f"/api/panel/scheduled-tasks/{task['id']}", headers=_auth_headers("user-1"))
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized"

    response = client.post(f"/api/panel/scheduled-tasks/{task['id']}/run", headers=_auth_headers("user-1"))
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized"


def test_cannot_create_scheduled_task_for_other_users_thread(monkeypatch, tmp_path):
    client, _service = _make_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/panel/scheduled-tasks",
        json={
            "thread_id": "thread-2",
            "name": "Cross-user task",
            "instruction": "Should fail.",
            "cron_expression": "0 9 * * *",
            "enabled": True,
        },
        headers=_auth_headers("user-1"),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized"
