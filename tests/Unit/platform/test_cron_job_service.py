"""Tests for cron_job_service — cron_jobs CRUD with SQLite storage."""

import pytest

from backend.web.services import cron_job_service


def _require_job(job: dict | None) -> dict:
    assert job is not None
    return job


@pytest.fixture(autouse=True)
def _use_tmp_db(tmp_path, monkeypatch):
    """Redirect cron_job_service to a temporary SQLite database."""
    from storage.providers.sqlite.cron_job_repo import SQLiteCronJobRepo

    db_path = tmp_path / "test.db"
    monkeypatch.setattr(cron_job_service, "make_cron_job_repo", lambda: SQLiteCronJobRepo(db_path=db_path))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_create_raises_on_empty_name(self):
        with pytest.raises(ValueError, match="name"):
            cron_job_service.create_cron_job(name="", cron_expression="*/5 * * * *")

    def test_create_raises_on_empty_cron_expression(self):
        with pytest.raises(ValueError, match="cron_expression"):
            cron_job_service.create_cron_job(name="my job", cron_expression="")

    def test_create_raises_on_whitespace_name(self):
        with pytest.raises(ValueError, match="name"):
            cron_job_service.create_cron_job(name="   ", cron_expression="*/5 * * * *")

    def test_create_raises_on_whitespace_cron_expression(self):
        with pytest.raises(ValueError, match="cron_expression"):
            cron_job_service.create_cron_job(name="my job", cron_expression="   ")


# ---------------------------------------------------------------------------
# create_cron_job
# ---------------------------------------------------------------------------


class TestCreateCronJob:
    def test_basic_fields(self):
        job = cron_job_service.create_cron_job(name="nightly backup", cron_expression="0 2 * * *")
        assert job["name"] == "nightly backup"
        assert job["cron_expression"] == "0 2 * * *"
        assert job["id"]  # non-empty
        assert job["created_at"] > 0

    def test_default_values(self):
        job = cron_job_service.create_cron_job(name="defaults", cron_expression="*/10 * * * *")
        assert job["description"] == ""
        assert job["task_template"] == "{}"
        assert job["enabled"] == 1
        assert job["last_run_at"] == 0
        assert job["next_run_at"] == 0

    def test_custom_fields(self):
        job = cron_job_service.create_cron_job(
            name="custom",
            cron_expression="0 * * * *",
            description="hourly sync",
            task_template='{"title":"sync"}',
            enabled=0,
        )
        assert job["description"] == "hourly sync"
        assert job["task_template"] == '{"title":"sync"}'
        assert job["enabled"] == 0


# ---------------------------------------------------------------------------
# get_cron_job
# ---------------------------------------------------------------------------


class TestGetCronJob:
    def test_get_existing(self):
        job = cron_job_service.create_cron_job(name="fetchable", cron_expression="0 0 * * *")
        fetched = cron_job_service.get_cron_job(job["id"])
        assert fetched is not None
        assert fetched["name"] == "fetchable"

    def test_get_nonexistent_returns_none(self):
        assert cron_job_service.get_cron_job("nonexistent_id") is None


# ---------------------------------------------------------------------------
# list_cron_jobs
# ---------------------------------------------------------------------------


class TestListCronJobs:
    def test_list_returns_all(self):
        cron_job_service.create_cron_job(name="a", cron_expression="* * * * *")
        cron_job_service.create_cron_job(name="b", cron_expression="* * * * *")
        jobs = cron_job_service.list_cron_jobs()
        assert len(jobs) >= 2

    def test_list_ordered_by_created_at_desc(self):
        cron_job_service.create_cron_job(name="first", cron_expression="* * * * *")
        cron_job_service.create_cron_job(name="second", cron_expression="* * * * *")
        jobs = cron_job_service.list_cron_jobs()
        assert jobs[0]["created_at"] >= jobs[1]["created_at"]

    def test_list_empty(self):
        jobs = cron_job_service.list_cron_jobs()
        assert jobs == []


# ---------------------------------------------------------------------------
# update_cron_job
# ---------------------------------------------------------------------------


class TestUpdateCronJob:
    def test_update_name(self):
        job = cron_job_service.create_cron_job(name="original", cron_expression="* * * * *")
        updated = _require_job(cron_job_service.update_cron_job(job["id"], name="renamed"))
        assert updated["name"] == "renamed"

    def test_update_cron_expression(self):
        job = cron_job_service.create_cron_job(name="expr", cron_expression="* * * * *")
        updated = _require_job(cron_job_service.update_cron_job(job["id"], cron_expression="0 0 * * *"))
        assert updated["cron_expression"] == "0 0 * * *"

    def test_update_enabled(self):
        job = cron_job_service.create_cron_job(name="toggle", cron_expression="* * * * *")
        updated = _require_job(cron_job_service.update_cron_job(job["id"], enabled=0))
        assert updated["enabled"] == 0

    def test_update_last_run_at(self):
        job = cron_job_service.create_cron_job(name="run tracker", cron_expression="* * * * *")
        updated = _require_job(cron_job_service.update_cron_job(job["id"], last_run_at=1234567890))
        assert updated["last_run_at"] == 1234567890

    def test_update_nonexistent_returns_none(self):
        result = cron_job_service.update_cron_job("ghost", name="nope")
        assert result is None

    def test_update_no_changes_returns_current(self):
        job = cron_job_service.create_cron_job(name="stable", cron_expression="* * * * *")
        result = cron_job_service.update_cron_job(job["id"])
        assert result is not None
        assert result["name"] == "stable"


# ---------------------------------------------------------------------------
# delete_cron_job
# ---------------------------------------------------------------------------


class TestDeleteCronJob:
    def test_delete_existing(self):
        job = cron_job_service.create_cron_job(name="to delete", cron_expression="* * * * *")
        assert cron_job_service.delete_cron_job(job["id"]) is True
        assert cron_job_service.get_cron_job(job["id"]) is None

    def test_delete_nonexistent_returns_false(self):
        assert cron_job_service.delete_cron_job("ghost") is False


# ---------------------------------------------------------------------------
# Full CRUD lifecycle
# ---------------------------------------------------------------------------


class TestCRUDLifecycle:
    def test_full_lifecycle(self):
        # Create
        job = cron_job_service.create_cron_job(
            name="lifecycle test",
            cron_expression="0 */6 * * *",
            description="every 6 hours",
        )
        job_id = job["id"]
        assert job["name"] == "lifecycle test"

        # Read
        fetched = cron_job_service.get_cron_job(job_id)
        assert fetched == job

        # List
        jobs = cron_job_service.list_cron_jobs()
        assert any(j["id"] == job_id for j in jobs)

        # Update
        updated = _require_job(cron_job_service.update_cron_job(job_id, name="updated name", enabled=0))
        assert updated["name"] == "updated name"
        assert updated["enabled"] == 0
        assert updated["description"] == "every 6 hours"  # unchanged

        # Delete
        assert cron_job_service.delete_cron_job(job_id) is True
        assert cron_job_service.get_cron_job(job_id) is None
        assert cron_job_service.delete_cron_job(job_id) is False
