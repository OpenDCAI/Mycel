"""Tests for task_service — panel_tasks CRUD with extended schema."""

import sqlite3
import time

import pytest

from backend.web.services import task_service


@pytest.fixture(autouse=True)
def _use_tmp_db(tmp_path, monkeypatch):
    """Redirect task_service to a temporary SQLite database."""
    from storage.providers.sqlite.panel_task_repo import SQLitePanelTaskRepo

    db_path = tmp_path / "test.db"
    monkeypatch.setattr(task_service, "make_panel_task_repo", lambda: SQLitePanelTaskRepo(db_path=db_path))


# ---------------------------------------------------------------------------
# Table schema
# ---------------------------------------------------------------------------


class TestSchema:
    def test_new_columns_present_on_created_task(self):
        task = task_service.create_task(title="schema check")
        for col in ("thread_id", "source", "cron_job_id", "result", "started_at", "completed_at"):
            assert col in task, f"missing column: {col}"

    def test_new_columns_have_correct_defaults(self):
        task = task_service.create_task(title="defaults check")
        assert task["thread_id"] == ""
        assert task["source"] == "manual"
        assert task["cron_job_id"] == ""
        assert task["result"] == ""
        assert task["started_at"] == 0
        assert task["completed_at"] == 0


# ---------------------------------------------------------------------------
# create_task
# ---------------------------------------------------------------------------


class TestCreateTask:
    def test_basic_fields(self):
        task = task_service.create_task(title="buy milk", priority="high")
        assert task["title"] == "buy milk"
        assert task["priority"] == "high"
        assert task["status"] == "pending"
        assert task["progress"] == 0

    def test_accepts_source(self):
        task = task_service.create_task(title="cron task", source="cron")
        assert task["source"] == "cron"

    def test_accepts_cron_job_id(self):
        task = task_service.create_task(title="scheduled", cron_job_id="cj_123")
        assert task["cron_job_id"] == "cj_123"

    def test_accepts_thread_id(self):
        task = task_service.create_task(title="agent task", thread_id="th_abc")
        assert task["thread_id"] == "th_abc"


# ---------------------------------------------------------------------------
# update_task
# ---------------------------------------------------------------------------


class TestUpdateTask:
    def test_update_title_and_status(self):
        task = task_service.create_task(title="original")
        updated = task_service.update_task(task["id"], title="changed", status="in_progress")
        assert updated["title"] == "changed"
        assert updated["status"] == "in_progress"

    def test_update_progress(self):
        task = task_service.create_task(title="progress test")
        updated = task_service.update_task(task["id"], progress=50)
        assert updated["progress"] == 50

    def test_update_thread_id(self):
        task = task_service.create_task(title="link thread")
        updated = task_service.update_task(task["id"], thread_id="th_999")
        assert updated["thread_id"] == "th_999"

    def test_update_result(self):
        task = task_service.create_task(title="result test")
        updated = task_service.update_task(task["id"], result="done: 3 files changed")
        assert updated["result"] == "done: 3 files changed"

    def test_update_started_at(self):
        task = task_service.create_task(title="timing test")
        now = int(time.time() * 1000)
        updated = task_service.update_task(task["id"], started_at=now)
        assert updated["started_at"] == now

    def test_update_completed_at(self):
        task = task_service.create_task(title="timing test 2")
        now = int(time.time() * 1000)
        updated = task_service.update_task(task["id"], completed_at=now)
        assert updated["completed_at"] == now

    def test_update_nonexistent_returns_none(self):
        result = task_service.update_task("nonexistent", title="nope")
        assert result is None


# ---------------------------------------------------------------------------
# list / delete / bulk_update
# ---------------------------------------------------------------------------


class TestListDeleteBulk:
    def test_list_returns_all(self):
        task_service.create_task(title="a")
        task_service.create_task(title="b")
        tasks = task_service.list_tasks()
        assert len(tasks) >= 2

    def test_delete_existing(self):
        task = task_service.create_task(title="to delete")
        assert task_service.delete_task(task["id"]) is True
        tasks = task_service.list_tasks()
        assert all(t["id"] != task["id"] for t in tasks)

    def test_delete_nonexistent(self):
        assert task_service.delete_task("ghost") is False

    def test_bulk_update_completed(self):
        t1 = task_service.create_task(title="bulk1")
        t2 = task_service.create_task(title="bulk2")
        count = task_service.bulk_update_task_status([t1["id"], t2["id"]], "completed")
        assert count == 2
        tasks = {t["id"]: t for t in task_service.list_tasks()}
        assert tasks[t1["id"]]["progress"] == 100
        assert tasks[t2["id"]]["status"] == "completed"


# ---------------------------------------------------------------------------
# Migration — existing DB without new columns
# ---------------------------------------------------------------------------


class TestMigration:
    def test_old_table_gets_new_columns(self, tmp_path, monkeypatch):
        """Simulate an old DB that lacks the new columns."""
        from storage.providers.sqlite.panel_task_repo import SQLitePanelTaskRepo

        db_path = tmp_path / "legacy.db"
        monkeypatch.setattr(task_service, "make_panel_task_repo", lambda: SQLitePanelTaskRepo(db_path=db_path))

        # Create the old schema directly
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE panel_tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                assignee_id TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                priority TEXT DEFAULT 'medium',
                progress INTEGER DEFAULT 0,
                deadline TEXT DEFAULT '',
                created_at INTEGER NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO panel_tasks (id,title,created_at) VALUES (?,?,?)",
            ("old_1", "legacy task", int(time.time() * 1000)),
        )
        conn.commit()
        conn.close()

        # Now open through task_service — migration should add columns
        tasks = task_service.list_tasks()
        assert len(tasks) == 1
        task = tasks[0]
        assert task["thread_id"] == ""
        assert task["source"] == "manual"
        assert task["cron_job_id"] == ""
        assert task["result"] == ""
        assert task["started_at"] == 0
        assert task["completed_at"] == 0
