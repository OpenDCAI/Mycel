"""Task CRUD — repo-backed panel_tasks service."""

from typing import Any

from backend.web.core.storage_factory import make_panel_task_repo


def _repo() -> Any:
    return make_panel_task_repo()


def list_tasks(owner_user_id: str | None = None, repo: Any = None) -> list[dict[str, Any]]:
    own_repo = repo is None
    repo = repo or _repo()
    try:
        return repo.list_all(owner_user_id=owner_user_id)
    finally:
        if own_repo:
            repo.close()


def get_task(task_id: str, owner_user_id: str | None = None, repo: Any = None) -> dict[str, Any] | None:
    own_repo = repo is None
    repo = repo or _repo()
    try:
        return repo.get(task_id, owner_user_id=owner_user_id)
    finally:
        if own_repo:
            repo.close()


def get_highest_priority_pending_task(owner_user_id: str | None = None, repo: Any = None) -> dict[str, Any] | None:
    own_repo = repo is None
    repo = repo or _repo()
    try:
        return repo.get_highest_priority_pending(owner_user_id=owner_user_id)
    finally:
        if own_repo:
            repo.close()


def create_task(repo: Any = None, **fields: Any) -> dict[str, Any]:
    own_repo = repo is None
    repo = repo or _repo()
    try:
        return repo.create(**fields)
    finally:
        if own_repo:
            repo.close()


def update_task(task_id: str, owner_user_id: str | None = None, repo: Any = None, **fields: Any) -> dict[str, Any] | None:
    own_repo = repo is None
    repo = repo or _repo()
    try:
        return repo.update(task_id, owner_user_id=owner_user_id, **fields)
    finally:
        if own_repo:
            repo.close()


def delete_task(task_id: str, owner_user_id: str | None = None, repo: Any = None) -> bool:
    own_repo = repo is None
    repo = repo or _repo()
    try:
        return repo.delete(task_id, owner_user_id=owner_user_id)
    finally:
        if own_repo:
            repo.close()


def bulk_delete_tasks(ids: list[str], owner_user_id: str | None = None, repo: Any = None) -> int:
    own_repo = repo is None
    repo = repo or _repo()
    try:
        return repo.bulk_delete(ids, owner_user_id=owner_user_id)
    finally:
        if own_repo:
            repo.close()


def bulk_update_task_status(ids: list[str], status: str, owner_user_id: str | None = None, repo: Any = None) -> int:
    own_repo = repo is None
    repo = repo or _repo()
    try:
        return repo.bulk_update_status(ids, status, owner_user_id=owner_user_id)
    finally:
        if own_repo:
            repo.close()
