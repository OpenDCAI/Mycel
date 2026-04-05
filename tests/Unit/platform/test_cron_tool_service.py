"""Tests for CronToolService — agent-callable cron CRUD surface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from core.runtime.registry import ToolRegistry
from core.tools.cron.service import CronToolService


def _redirect_cron_repo(monkeypatch, tmp_path: Path) -> None:
    from storage.providers.sqlite.cron_job_repo import SQLiteCronJobRepo

    db_path = tmp_path / "cron-tools.db"
    monkeypatch.setattr(
        "backend.web.services.cron_job_service.make_cron_job_repo",
        lambda: SQLiteCronJobRepo(db_path=db_path),
    )


def test_cron_tool_registry_exposes_canonical_surface(monkeypatch, tmp_path: Path) -> None:
    _redirect_cron_repo(monkeypatch, tmp_path)
    registry = ToolRegistry()

    CronToolService(registry)

    for tool_name in ("CronCreate", "CronDelete", "CronList"):
        assert registry.get(tool_name) is not None


def test_cron_create_list_delete_roundtrip(monkeypatch, tmp_path: Path) -> None:
    _redirect_cron_repo(monkeypatch, tmp_path)
    registry = ToolRegistry()

    CronToolService(registry)

    create = registry.get("CronCreate")
    list_jobs = registry.get("CronList")
    delete = registry.get("CronDelete")

    assert create is not None
    assert list_jobs is not None
    assert delete is not None

    created_raw = create.handler(
        name="nightly backup",
        cron_expression="0 2 * * *",
        description="backup prod",
        task_template='{"title":"backup"}',
        enabled=True,
    )
    created = json.loads(cast(str, created_raw))
    job = created["item"]
    assert job["name"] == "nightly backup"
    assert job["cron_expression"] == "0 2 * * *"

    listed = json.loads(cast(str, list_jobs.handler()))
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == job["id"]

    deleted = json.loads(cast(str, delete.handler(job_id=job["id"])))
    assert deleted == {"ok": True, "id": job["id"]}

    listed_after = json.loads(cast(str, list_jobs.handler()))
    assert listed_after == {"items": [], "total": 0}


def test_cron_create_requires_valid_json_template(monkeypatch, tmp_path: Path) -> None:
    _redirect_cron_repo(monkeypatch, tmp_path)
    registry = ToolRegistry()

    CronToolService(registry)
    create = registry.get("CronCreate")
    assert create is not None

    try:
        create.handler(
            name="broken",
            cron_expression="0 2 * * *",
            task_template="{not json}",
        )
    except ValueError as exc:
        assert "task_template must be valid JSON" in str(exc)
    else:
        raise AssertionError("CronCreate should fail loudly on invalid JSON")
