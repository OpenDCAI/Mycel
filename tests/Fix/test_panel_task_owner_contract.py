from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from backend.web.models.panel import BulkDeleteTasksRequest, BulkTaskStatusRequest, UpdateCronJobRequest, UpdateTaskRequest
from backend.web.routers import panel as panel_router
from backend.web.services import cron_job_service, task_service
from backend.web.services.cron_service import CronService


@pytest.mark.asyncio
async def test_panel_task_mutations_forward_owner_scope(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, Any] = {}

    def fake_bulk_update(ids: list[str], status: str, owner_user_id: str | None = None) -> int:
        seen["bulk_status"] = (ids, status, owner_user_id)
        return len(ids)

    def fake_bulk_delete(ids: list[str], owner_user_id: str | None = None) -> int:
        seen["bulk_delete"] = (ids, owner_user_id)
        return len(ids)

    def fake_update(task_id: str, owner_user_id: str | None = None, **fields: Any) -> dict[str, Any]:
        seen["update"] = (task_id, owner_user_id, fields)
        return {"id": task_id, **fields}

    def fake_delete(task_id: str, owner_user_id: str | None = None) -> bool:
        seen["delete"] = (task_id, owner_user_id)
        return True

    monkeypatch.setattr(panel_router.task_service, "bulk_update_task_status", fake_bulk_update)
    monkeypatch.setattr(panel_router.task_service, "bulk_delete_tasks", fake_bulk_delete)
    monkeypatch.setattr(panel_router.task_service, "update_task", fake_update)
    monkeypatch.setattr(panel_router.task_service, "delete_task", fake_delete)

    await panel_router.bulk_update_status(BulkTaskStatusRequest(ids=["t-1"], status="completed"), user_id="user-1")
    await panel_router.bulk_delete_tasks(BulkDeleteTasksRequest(ids=["t-2"]), user_id="user-1")
    await panel_router.update_task("t-3", UpdateTaskRequest(title="new"), user_id="user-1")
    await panel_router.delete_task("t-4", user_id="user-1")

    assert seen["bulk_status"] == (["t-1"], "completed", "user-1")
    assert seen["bulk_delete"] == (["t-2"], "user-1")
    assert seen["update"][0:2] == ("t-3", "user-1")
    assert seen["update"][2]["title"] == "new"
    assert seen["delete"] == ("t-4", "user-1")


@pytest.mark.asyncio
async def test_panel_cron_mutations_forward_owner_scope(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, Any] = {}

    def fake_update(job_id: str, owner_user_id: str | None = None, **fields: Any) -> dict[str, Any]:
        seen["update"] = (job_id, owner_user_id, fields)
        return {"id": job_id, **fields}

    def fake_delete(job_id: str, owner_user_id: str | None = None) -> bool:
        seen["delete"] = (job_id, owner_user_id)
        return True

    class _FakeCronService:
        async def trigger_job(self, job_id: str, owner_user_id: str | None = None) -> dict[str, Any]:
            seen["trigger"] = (job_id, owner_user_id)
            return {"id": "task-1", "job_id": job_id, "owner_user_id": owner_user_id}

    monkeypatch.setattr(panel_router.cron_job_service, "update_cron_job", fake_update)
    monkeypatch.setattr(panel_router.cron_job_service, "delete_cron_job", fake_delete)

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(cron_service=_FakeCronService())))

    await panel_router.update_cron_job("job-1", UpdateCronJobRequest(description="desc"), user_id="user-1")
    await panel_router.delete_cron_job("job-2", user_id="user-1")
    result = await panel_router.trigger_cron_job("job-3", request=request, user_id="user-1")

    assert seen["update"] == ("job-1", "user-1", {"description": "desc"})
    assert seen["delete"] == ("job-2", "user-1")
    assert seen["trigger"] == ("job-3", "user-1")
    assert result["item"]["owner_user_id"] == "user-1"


@pytest.mark.asyncio
async def test_cron_trigger_copies_job_owner_to_created_task(monkeypatch: pytest.MonkeyPatch):
    def fake_get(job_id: str, owner_user_id: str | None = None) -> dict[str, Any]:
        return {
            "id": job_id,
            "enabled": 1,
            "owner_user_id": "owner-7",
            "task_template": "{\"title\": \"From cron\"}",
        }

    created: dict[str, Any] = {}

    def fake_create_task(**fields: Any) -> dict[str, Any]:
        created.update(fields)
        return {"id": "task-1", **fields}

    def fake_update_job(job_id: str, owner_user_id: str | None = None, **fields: Any) -> dict[str, Any]:
        return {"id": job_id, "owner_user_id": owner_user_id, **fields}

    monkeypatch.setattr("backend.web.services.cron_service.cron_job_service.get_cron_job", fake_get)
    monkeypatch.setattr("backend.web.services.cron_service.task_service.create_task", fake_create_task)
    monkeypatch.setattr("backend.web.services.cron_service.cron_job_service.update_cron_job", fake_update_job)

    task = await CronService().trigger_job("job-1")

    assert task is not None
    assert created["owner_user_id"] == "owner-7"
    assert created["source"] == "cron"
    assert created["cron_job_id"] == "job-1"


def test_task_service_forwards_owner_scope_to_repo(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, Any] = {}

    class _FakeRepo:
        def close(self) -> None:
            return None

        def get(self, task_id: str, owner_user_id: str | None = None) -> dict[str, Any]:
            seen["get"] = (task_id, owner_user_id)
            return {"id": task_id}

        def update(self, task_id: str, owner_user_id: str | None = None, **fields: Any) -> dict[str, Any]:
            seen["update"] = (task_id, owner_user_id, fields)
            return {"id": task_id, **fields}

        def delete(self, task_id: str, owner_user_id: str | None = None) -> bool:
            seen["delete"] = (task_id, owner_user_id)
            return True

        def bulk_delete(self, ids: list[str], owner_user_id: str | None = None) -> int:
            seen["bulk_delete"] = (ids, owner_user_id)
            return len(ids)

        def bulk_update_status(self, ids: list[str], status: str, owner_user_id: str | None = None) -> int:
            seen["bulk_status"] = (ids, status, owner_user_id)
            return len(ids)

    monkeypatch.setattr(task_service, "_repo", lambda: _FakeRepo())

    task_service.get_task("t-1", owner_user_id="user-1")
    task_service.update_task("t-2", owner_user_id="user-1", title="new")
    task_service.delete_task("t-3", owner_user_id="user-1")
    task_service.bulk_delete_tasks(["t-4"], owner_user_id="user-1")
    task_service.bulk_update_task_status(["t-5"], "completed", owner_user_id="user-1")

    assert seen["get"] == ("t-1", "user-1")
    assert seen["update"] == ("t-2", "user-1", {"title": "new"})
    assert seen["delete"] == ("t-3", "user-1")
    assert seen["bulk_delete"] == (["t-4"], "user-1")
    assert seen["bulk_status"] == (["t-5"], "completed", "user-1")


def test_cron_job_service_forwards_owner_scope_to_repo(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, Any] = {}

    class _FakeRepo:
        def close(self) -> None:
            return None

        def get(self, job_id: str, owner_user_id: str | None = None) -> dict[str, Any]:
            seen["get"] = (job_id, owner_user_id)
            return {"id": job_id}

        def update(self, job_id: str, owner_user_id: str | None = None, **fields: Any) -> dict[str, Any]:
            seen["update"] = (job_id, owner_user_id, fields)
            return {"id": job_id, **fields}

        def delete(self, job_id: str, owner_user_id: str | None = None) -> bool:
            seen["delete"] = (job_id, owner_user_id)
            return True

    monkeypatch.setattr(cron_job_service, "_repo", lambda: _FakeRepo())

    cron_job_service.get_cron_job("job-1", owner_user_id="user-1")
    cron_job_service.update_cron_job("job-2", owner_user_id="user-1", description="desc")
    cron_job_service.delete_cron_job("job-3", owner_user_id="user-1")

    assert seen["get"] == ("job-1", "user-1")
    assert seen["update"] == ("job-2", "user-1", {"description": "desc"})
    assert seen["delete"] == ("job-3", "user-1")
