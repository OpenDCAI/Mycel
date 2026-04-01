"""Task CRUD — repo-backed panel_tasks service."""

from typing import Any

from backend.web.core.config import DB_PATH
from storage.providers.sqlite.panel_task_repo import SQLitePanelTaskRepo


def _repo() -> SQLitePanelTaskRepo:
    return SQLitePanelTaskRepo(db_path=DB_PATH)


def list_tasks() -> list[dict[str, Any]]:
    repo = _repo()
    try:
        return repo.list_all()
    finally:
        repo.close()


def get_task(task_id: str) -> dict[str, Any] | None:
    repo = _repo()
    try:
        return repo.get(task_id)
    finally:
        repo.close()


def get_highest_priority_pending_task() -> dict[str, Any] | None:
    """Return the highest-priority pending task (high > medium > low, oldest first)."""
    repo = _repo()
    try:
        return repo.get_highest_priority_pending()
    finally:
        repo.close()


def create_task(**fields: Any) -> dict[str, Any]:
    repo = _repo()
    try:
        return repo.create(**fields)
    finally:
        repo.close()


def update_task(task_id: str, **fields: Any) -> dict[str, Any] | None:
    repo = _repo()
    try:
        return repo.update(task_id, **fields)
    finally:
        repo.close()


def delete_task(task_id: str) -> bool:
    repo = _repo()
    try:
        return repo.delete(task_id)
    finally:
        repo.close()


def bulk_delete_tasks(ids: list[str]) -> int:
    repo = _repo()
    try:
        return repo.bulk_delete(ids)
    finally:
        repo.close()


def bulk_update_task_status(ids: list[str], status: str) -> int:
    repo = _repo()
    try:
        return repo.bulk_update_status(ids, status)
    finally:
        repo.close()
