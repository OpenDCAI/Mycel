"""Tests for CronService — background cron scheduler that creates tasks."""

import json
import time

import pytest

from backend.web.services import cron_job_service, task_service
from backend.web.services.cron_service import CronService


@pytest.fixture(autouse=True)
def _use_tmp_db(tmp_path, monkeypatch):
    """Redirect both cron_job_service and task_service to a temp DB."""
    from storage.providers.sqlite.cron_job_repo import SQLiteCronJobRepo
    from storage.providers.sqlite.panel_task_repo import SQLitePanelTaskRepo

    db_path = tmp_path / "test.db"
    monkeypatch.setattr(cron_job_service, "make_cron_job_repo", lambda: SQLiteCronJobRepo(db_path=db_path))
    monkeypatch.setattr(task_service, "make_panel_task_repo", lambda: SQLitePanelTaskRepo(db_path=db_path))


@pytest.fixture
def cron_svc():
    return CronService()


def _make_job(
    *,
    name: str = "test job",
    cron_expression: str = "*/5 * * * *",
    enabled: int = 1,
    task_template: str | None = None,
) -> dict:
    """Helper: create a cron job and return it."""
    tpl = task_template or json.dumps({"title": f"Task from {name}", "priority": "high"})
    return cron_job_service.create_cron_job(
        name=name,
        cron_expression=cron_expression,
        enabled=enabled,
        task_template=tpl,
    )


# ---------------------------------------------------------------------------
# trigger_job
# ---------------------------------------------------------------------------


class TestTriggerJob:
    @pytest.mark.asyncio
    async def test_trigger_job_creates_task(self, cron_svc):
        """Triggering an enabled job creates a panel_task with correct fields."""
        job = _make_job(name="nightly build")
        result = await cron_svc.trigger_job(job["id"])

        assert result is not None
        assert result["source"] == "cron"
        assert result["cron_job_id"] == job["id"]
        assert result["title"] == "Task from nightly build"
        assert result["priority"] == "high"
        assert result["status"] == "pending"

        # Verify task actually exists in DB
        tasks = task_service.list_tasks()
        assert any(t["id"] == result["id"] for t in tasks)

    @pytest.mark.asyncio
    async def test_trigger_disabled_job_returns_none(self, cron_svc):
        """Triggering a disabled job returns None and creates no task."""
        job = _make_job(name="disabled job", enabled=0)
        result = await cron_svc.trigger_job(job["id"])

        assert result is None

        # No task should have been created
        tasks = task_service.list_tasks()
        assert not any(t["cron_job_id"] == job["id"] for t in tasks)

    @pytest.mark.asyncio
    async def test_trigger_updates_last_run_at(self, cron_svc):
        """Triggering a job updates its last_run_at timestamp."""
        job = _make_job(name="timestamp check")
        assert job["last_run_at"] == 0

        before = int(time.time() * 1000)
        await cron_svc.trigger_job(job["id"])
        after = int(time.time() * 1000)

        updated_job = cron_job_service.get_cron_job(job["id"])
        assert updated_job is not None
        assert before <= updated_job["last_run_at"] <= after

    @pytest.mark.asyncio
    async def test_trigger_nonexistent_job_returns_none(self, cron_svc):
        """Triggering a nonexistent job returns None."""
        result = await cron_svc.trigger_job("nonexistent_id_999")
        assert result is None

    @pytest.mark.asyncio
    async def test_trigger_with_minimal_template(self, cron_svc):
        """A template with only a title still creates a valid task."""
        job = _make_job(
            name="minimal",
            task_template=json.dumps({"title": "Minimal task"}),
        )
        result = await cron_svc.trigger_job(job["id"])
        assert result is not None
        assert result["title"] == "Minimal task"
        assert result["source"] == "cron"

    @pytest.mark.asyncio
    async def test_trigger_with_empty_template(self, cron_svc):
        """An empty template {} still creates a task with defaults."""
        job = _make_job(name="empty template", task_template="{}")
        result = await cron_svc.trigger_job(job["id"])
        assert result is not None
        assert result["source"] == "cron"
        assert result["cron_job_id"] == job["id"]

    @pytest.mark.asyncio
    async def test_trigger_with_invalid_json_template_returns_none(self, cron_svc):
        """A job with malformed JSON template returns None gracefully."""
        job = _make_job(name="bad json", task_template="not-valid-json{{{")
        result = await cron_svc.trigger_job(job["id"])
        assert result is None


# ---------------------------------------------------------------------------
# is_due
# ---------------------------------------------------------------------------


class TestIsDue:
    def test_job_is_due_when_never_run(self, cron_svc):
        """A job that has never run (last_run_at=0) is due immediately."""
        job = _make_job(cron_expression="*/1 * * * *")  # every minute
        assert cron_svc.is_due(job) is True

    def test_job_not_due_when_recently_run(self, cron_svc):
        """A job that just ran is not due yet."""
        job = _make_job(cron_expression="0 0 * * *")  # daily at midnight
        # Simulate it was run 1 second ago
        now_ms = int(time.time() * 1000)
        cron_job_service.update_cron_job(job["id"], last_run_at=now_ms)
        job = cron_job_service.get_cron_job(job["id"])
        assert cron_svc.is_due(job) is False

    def test_disabled_job_is_never_due(self, cron_svc):
        """A disabled job is never due, regardless of timing."""
        job = _make_job(cron_expression="*/1 * * * *", enabled=0)
        assert cron_svc.is_due(job) is False


# ---------------------------------------------------------------------------
# start / stop lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self, cron_svc):
        """CronService can start and stop without errors."""
        await cron_svc.start()
        assert cron_svc._running is True
        assert cron_svc._task is not None

        await cron_svc.stop()
        assert cron_svc._running is False

    @pytest.mark.asyncio
    async def test_stop_without_start(self, cron_svc):
        """Stopping a never-started service is a no-op."""
        await cron_svc.stop()  # should not raise
        assert cron_svc._running is False

    @pytest.mark.asyncio
    async def test_double_start(self, cron_svc):
        """Starting an already running service is idempotent."""
        await cron_svc.start()
        task1 = cron_svc._task
        await cron_svc.start()  # should be no-op
        assert cron_svc._task is task1  # same task, not a new one
        await cron_svc.stop()
