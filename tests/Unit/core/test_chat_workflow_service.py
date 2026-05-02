from __future__ import annotations

from typing import Any

from core.work_item.chat_workflow.service import (
    ChatTaskService,
    ChatWorkflowEventService,
    ChatWorkflowService,
)
from core.work_item.types import WorkItem
from storage.contracts import ChatWorkflowEventRow, ChatWorkflowRow


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


class _WorkflowEventRepo:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, ChatWorkflowEventRow]] = {}

    def next_id(self, scope_id: str) -> str:
        return str(len(self.rows.get(scope_id, {})) + 1)

    def get(self, scope_id: str, event_id: str) -> ChatWorkflowEventRow | None:
        return self.rows.get(scope_id, {}).get(event_id)

    def list_all(self, scope_id: str) -> list[ChatWorkflowEventRow]:
        return list(self.rows.get(scope_id, {}).values())

    def insert(self, scope_id: str, event: ChatWorkflowEventRow) -> None:
        self.rows.setdefault(scope_id, {})[event.event_id] = event

    def update(self, scope_id: str, event: ChatWorkflowEventRow) -> None:
        self.rows.setdefault(scope_id, {})[event.event_id] = event

    def delete(self, scope_id: str, event_id: str) -> None:
        self.rows.get(scope_id, {}).pop(event_id, None)


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
        status="proposed",
        owner="reviewer-user",
        blocks=["2"],
        blocked_by=["0"],
    )
    other = service.create_task(
        "chat-2",
        subject="Separate room task",
        description="This must not appear in chat-1.",
    )

    assert task["id"] == "1"
    assert task["status"] == "proposed"
    assert task["blocks"] == ["2"]
    assert task["blockedBy"] == ["0"]
    updated = service.update_task("chat-1", "1", blocks=["3"], blocked_by=[])
    assert updated is not None
    assert updated["blocks"] == ["3"]
    assert updated["blockedBy"] == []
    assert other["id"] == "1"
    assert [row["subject"] for row in service.list_tasks("chat-1")] == ["Review worker patch"]
    assert [row["subject"] for row in service.list_tasks("chat-2")] == ["Separate room task"]


def test_chat_workflow_event_service_keeps_events_scoped_to_chat_id() -> None:
    repo = _WorkflowEventRepo()
    service = ChatWorkflowEventService(repo)

    event = service.create_event(
        "chat-1",
        kind="task_proposed_review",
        resource_refs=[{"type": "task", "id": "1"}],
        requested_by_user_id="supervisor-user",
        metadata={"rationale_ref": "msg-1"},
    )
    other = service.create_event(
        "chat-2",
        kind="group_stop",
        resource_refs=[{"type": "group", "id": "group"}],
    )

    assert event["event_id"] == "1"
    assert event["state"] == "open"
    assert event["resource_refs"] == [{"type": "task", "id": "1"}]
    assert event["requested_by_user_id"] == "supervisor-user"
    assert service.list_events("chat-1") == [event]
    assert service.list_events("chat-2") == [other]

    updated = service.update_event(
        "chat-1",
        "1",
        decision_states={"reviewer-user": {"1": "pending"}},
        state="settled",
        final_state={"1": "pending"},
        settled_at=42.0,
    )

    assert updated is not None
    assert updated["state"] == "settled"
    assert updated["decision_states"] == {"reviewer-user": {"1": "pending"}}
    assert updated["final_state"] == {"1": "pending"}
    assert updated["settled_at"] == 42.0
