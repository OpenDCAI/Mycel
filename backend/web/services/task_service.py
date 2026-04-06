"""Task CRUD — repo-backed panel_tasks service."""

from typing import Any

from backend.web.core.storage_factory import make_panel_task_repo
from storage.runtime import build_thread_repo


def _repo() -> Any:
    return make_panel_task_repo()


def list_tasks(owner_user_id: str | None = None, repo: Any = None, thread_repo: Any = None) -> list[dict[str, Any]]:
    own_repo = repo is None
    repo = repo or _repo()
    try:
        return _enrich_task_thread_members(repo.list_all(owner_user_id=owner_user_id), thread_repo=thread_repo)
    finally:
        if own_repo:
            repo.close()


def _enrich_task_thread_members(tasks: list[dict[str, Any]], thread_repo: Any = None) -> list[dict[str, Any]]:
    thread_ids = [str(task.get("thread_id") or "").strip() for task in tasks]
    thread_ids = [thread_id for thread_id in dict.fromkeys(thread_ids) if thread_id]
    if not thread_ids:
        return tasks

    # @@@task-thread-member-enrichment - panel tasks persist thread_id only, so enrich member_id
    # from canonical thread metadata before frontend deep-links are rendered.
    own_thread_repo = thread_repo is None
    thread_repo = thread_repo or build_thread_repo()
    try:
        member_ids = {thread_id: (thread_repo.get_by_id(thread_id) or {}).get("member_id") for thread_id in thread_ids}
    finally:
        if own_thread_repo:
            thread_repo.close()

    enriched: list[dict[str, Any]] = []
    for task in tasks:
        thread_id = str(task.get("thread_id") or "").strip()
        if thread_id and member_ids.get(thread_id):
            enriched.append({**task, "member_id": member_ids[thread_id]})
        else:
            enriched.append(task)
    return enriched


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
