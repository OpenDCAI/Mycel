from __future__ import annotations

from typing import Any

from core.work_item.types import WorkItem


class ChatWorkflowService:
    def __init__(self, workflow_repo: Any) -> None:
        self._repo = workflow_repo

    def get_workflow(self, chat_id: str) -> dict[str, Any] | None:
        row = self._repo.get(chat_id)
        return _workflow_response(row) if row is not None else None

    def set_workflow(
        self,
        chat_id: str,
        *,
        kind: str,
        state: str = "active",
        config: dict[str, Any] | None = None,
        updated_by_user_id: str | None = None,
    ) -> dict[str, Any]:
        return _workflow_response(
            self._repo.upsert(
                chat_id,
                kind=kind,
                state=state,
                config=config or {},
                updated_by_user_id=updated_by_user_id,
            )
        )

    def delete_workflow(self, chat_id: str) -> None:
        self._repo.delete(chat_id)


class ChatTaskService:
    def __init__(self, task_repo: Any) -> None:
        self._repo = task_repo

    def list_tasks(self, chat_id: str) -> list[dict[str, Any]]:
        return [_task_response(item) for item in self._repo.list_all(chat_id)]

    def get_task(self, chat_id: str, task_id: str) -> dict[str, Any] | None:
        item = self._repo.get(chat_id, task_id)
        return _task_response(item) if item is not None else None

    def create_task(
        self,
        chat_id: str,
        *,
        subject: str,
        description: str,
        status: str = "pending",
        active_form: str | None = None,
        owner: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = WorkItem(
            id=self._repo.next_id(chat_id),
            subject=subject,
            description=description,
            status=status,
            active_form=active_form,
            owner=owner,
            metadata=metadata or {},
        )
        self._repo.insert(chat_id, item)
        return _task_response(item)

    def update_task(
        self,
        chat_id: str,
        task_id: str,
        *,
        status: str | None = None,
        subject: str | None = None,
        description: str | None = None,
        active_form: str | None = None,
        owner: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        item = self._repo.get(chat_id, task_id)
        if item is None:
            return None
        if status is not None:
            item.status = status
        if subject is not None:
            item.subject = subject
        if description is not None:
            item.description = description
        if active_form is not None:
            item.active_form = active_form
        if owner is not None:
            item.owner = owner
        if metadata is not None:
            item.metadata = dict(metadata)
        self._repo.update(chat_id, item)
        return _task_response(item)

    def delete_task(self, chat_id: str, task_id: str) -> None:
        self._repo.delete(chat_id, task_id)


def _workflow_response(row: Any) -> dict[str, Any]:
    return {
        "chat_id": row.chat_id,
        "kind": row.kind,
        "state": row.state,
        "config": dict(row.config),
        "updated_by_user_id": row.updated_by_user_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _task_response(item: WorkItem) -> dict[str, Any]:
    payload = item.to_detail()
    payload["status"] = item.status.value if hasattr(item.status, "value") else str(item.status)
    return payload
