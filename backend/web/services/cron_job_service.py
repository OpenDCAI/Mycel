"""Cron Jobs CRUD — repo-backed service."""

from typing import Any

from storage.runtime import build_cron_job_repo


def _repo() -> Any:
    return build_cron_job_repo()


def list_cron_jobs(owner_user_id: str | None = None, repo: Any = None) -> list[dict[str, Any]]:
    own_repo = repo is None
    repo = repo or _repo()
    try:
        return repo.list_all(owner_user_id=owner_user_id)
    finally:
        if own_repo:
            repo.close()


def get_cron_job(job_id: str, owner_user_id: str | None = None, repo: Any = None) -> dict[str, Any] | None:
    own_repo = repo is None
    repo = repo or _repo()
    try:
        return repo.get(job_id, owner_user_id=owner_user_id)
    finally:
        if own_repo:
            repo.close()


def create_cron_job(*, name: str, cron_expression: str, repo: Any = None, **fields: Any) -> dict[str, Any]:
    if not name or not name.strip():
        raise ValueError("name must not be empty")
    if not cron_expression or not cron_expression.strip():
        raise ValueError("cron_expression must not be empty")
    own_repo = repo is None
    repo = repo or _repo()
    try:
        return repo.create(name=name, cron_expression=cron_expression, **fields)
    finally:
        if own_repo:
            repo.close()


def update_cron_job(job_id: str, owner_user_id: str | None = None, repo: Any = None, **fields: Any) -> dict[str, Any] | None:
    own_repo = repo is None
    repo = repo or _repo()
    try:
        return repo.update(job_id, owner_user_id=owner_user_id, **fields)
    finally:
        if own_repo:
            repo.close()


def delete_cron_job(job_id: str, owner_user_id: str | None = None, repo: Any = None) -> bool:
    own_repo = repo is None
    repo = repo or _repo()
    try:
        return repo.delete(job_id, owner_user_id=owner_user_id)
    finally:
        if own_repo:
            repo.close()
