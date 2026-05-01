from __future__ import annotations

from typing import Any

from core.work_item.chat_workflow.service import ChatTaskService, ChatWorkflowService
from core.work_item.types import WorkItem
from storage.contracts import ChatWorkflowRow


class _WorkflowRepo:
    def __init__(self) -> None:
        self.rows: dict[str, ChatWorkflowRow] = {}

    def get(self, chat_id: str) -> ChatWorkflowRow | None:
        return self.rows.get(chat_id)

    def upsert(
        self,
        chat_id: str,
        *,
        kind: str,
        state: str,
        config: dict[str, Any],
        updated_by_user_id: str | None = None,
    ) -> ChatWorkflowRow:
        row = ChatWorkflowRow(
            chat_id=chat_id,
            kind=kind,
            state=state,
            config=config,
            updated_by_user_id=updated_by_user_id,
            created_at=1.0,
            updated_at=2.0,
        )
        self.rows[chat_id] = row
        return row

    def delete(self, chat_id: str) -> None:
        self.rows.pop(chat_id, None)


class _TaskRepo:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, WorkItem]] = {}

    def next_id(self, scope_id: str) -> str:
        return str(len(self.rows.get(scope_id, {})) + 1)

    def get(self, scope_id: str, item_id: str) -> WorkItem | None:
        return self.rows.get(scope_id, {}).get(item_id)

    def list_all(self, scope_id: str) -> list[WorkItem]:
        return list(self.rows.get(scope_id, {}).values())

    def insert(self, scope_id: str, item: WorkItem) -> None:
        self.rows.setdefault(scope_id, {})[item.id] = item

    def update(self, scope_id: str, item: WorkItem) -> None:
        self.rows.setdefault(scope_id, {})[item.id] = item

    def delete(self, scope_id: str, item_id: str) -> None:
        self.rows.get(scope_id, {}).pop(item_id, None)


def test_chat_workflow_service_projects_explicit_chat_scope() -> None:
    repo = _WorkflowRepo()
    service = ChatWorkflowService(repo)

    created = service.set_workflow(
        "chat-1",
        kind="keep",
        state="active",
        config={"reviewer": "reviewer-user"},
        updated_by_user_id="human-user",
    )

    assert created["chat_id"] == "chat-1"
    assert created["config"] == {"reviewer": "reviewer-user"}
    assert service.get_workflow("chat-1") == created
    assert service.get_workflow("chat-2") is None


def test_chat_task_service_keeps_tasks_scoped_to_chat_id() -> None:
    repo = _TaskRepo()
    service = ChatTaskService(repo)

    task = service.create_task(
        "chat-1",
        subject="Review worker patch",
        description="Read the worker result and decide next step.",
        owner="reviewer-user",
    )
    other = service.create_task(
        "chat-2",
        subject="Separate room task",
        description="This must not appear in chat-1.",
    )

    assert task["id"] == "1"
    assert other["id"] == "1"
    assert [row["subject"] for row in service.list_tasks("chat-1")] == ["Review worker patch"]
    assert [row["subject"] for row in service.list_tasks("chat-2")] == ["Separate room task"]
