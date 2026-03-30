"""Cron Jobs CRUD — repo-backed service."""

from typing import Any

from storage.providers.sqlite.cron_job_repo import SQLiteCronJobRepo


def list_cron_jobs() -> list[dict[str, Any]]:
    repo = SQLiteCronJobRepo()
    try:
        return repo.list_all()
    finally:
        repo.close()


def get_cron_job(job_id: str) -> dict[str, Any] | None:
    repo = SQLiteCronJobRepo()
    try:
        return repo.get(job_id)
    finally:
        repo.close()


def create_cron_job(*, name: str, cron_expression: str, **fields: Any) -> dict[str, Any]:
    if not name or not name.strip():
        raise ValueError("name must not be empty")
    if not cron_expression or not cron_expression.strip():
        raise ValueError("cron_expression must not be empty")

    repo = SQLiteCronJobRepo()
    try:
        return repo.create(name=name, cron_expression=cron_expression, **fields)
    finally:
        repo.close()


def update_cron_job(job_id: str, **fields: Any) -> dict[str, Any] | None:
    repo = SQLiteCronJobRepo()
    try:
        return repo.update(job_id, **fields)
    finally:
        repo.close()


def delete_cron_job(job_id: str) -> bool:
    repo = SQLiteCronJobRepo()
    try:
        return repo.delete(job_id)
    finally:
        repo.close()
