"""Cron Jobs CRUD — repo-backed service."""

from typing import Any

from backend.web.core.config import DB_PATH
from storage.providers.sqlite.cron_job_repo import SQLiteCronJobRepo


def _repo() -> SQLiteCronJobRepo:
    return SQLiteCronJobRepo(db_path=DB_PATH)


def list_cron_jobs() -> list[dict[str, Any]]:
    repo = _repo()
    try:
        return repo.list_all()
    finally:
        repo.close()


def get_cron_job(job_id: str) -> dict[str, Any] | None:
    repo = _repo()
    try:
        return repo.get(job_id)
    finally:
        repo.close()


def create_cron_job(*, name: str, cron_expression: str, **fields: Any) -> dict[str, Any]:
    if not name or not name.strip():
        raise ValueError("name must not be empty")
    if not cron_expression or not cron_expression.strip():
        raise ValueError("cron_expression must not be empty")

    repo = _repo()
    try:
        return repo.create(name=name, cron_expression=cron_expression, **fields)
    finally:
        repo.close()


def update_cron_job(job_id: str, **fields: Any) -> dict[str, Any] | None:
    repo = _repo()
    try:
        return repo.update(job_id, **fields)
    finally:
        repo.close()


def delete_cron_job(job_id: str) -> bool:
    repo = _repo()
    try:
        return repo.delete(job_id)
    finally:
        repo.close()


# Allow tests to override DB_PATH via monkeypatch
__all__ = ["DB_PATH", "list_cron_jobs", "get_cron_job", "create_cron_job", "update_cron_job", "delete_cron_job"]
