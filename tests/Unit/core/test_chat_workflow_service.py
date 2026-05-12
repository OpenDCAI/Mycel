from __future__ import annotations

from typing import Any

from core.work_item.chat_workflow.service import (
    ChatTaskService,
    ChatWorkflowEventService,
    ChatWorkflowService,
)
from core.work_item.types import WorkItem
from storage.contracts import ChatWorkflowEventRow, ChatWorkflowRow
from storage.errors import (
    StaleChatWorkflowEventVersionError,
    StaleChatWorkflowVersionError,
)


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
        expected_state_version: int | None = None,
    ) -> ChatWorkflowRow:
        existing = self.rows.get(chat_id)
        existing_version = int(getattr(existing, "state_version", 0)) if existing is not None else None
        if expected_state_version is not None and existing_version != expected_state_version:
            raise StaleChatWorkflowVersionError(
                chat_id=chat_id,
                expected_state_version=expected_state_version,
                actual_state_version=existing_version,
            )
        row = ChatWorkflowRow(
            chat_id=chat_id,
            kind=kind,
            state=state,
            config=config,
            updated_by_user_id=updated_by_user_id,
            created_at=1.0,
            updated_at=2.0,
            state_version=0 if existing is None else existing.state_version + 1,
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

    def update(
        self,
        scope_id: str,
        event: ChatWorkflowEventRow,
        *,
        expected_state_version: int | None = None,
    ) -> ChatWorkflowEventRow:
        existing = self.rows.get(scope_id, {}).get(event.event_id)
        existing_version = int(getattr(existing, "state_version", 0)) if existing is not None else None
        if expected_state_version is not None and existing_version != expected_state_version:
            raise StaleChatWorkflowEventVersionError(
                chat_id=scope_id,
                event_id=event.event_id,
                expected_state_version=expected_state_version,
                actual_state_version=existing_version,
            )
        updated = event.model_copy(update={"state_version": 0 if existing is None else existing.state_version + 1})
        self.rows.setdefault(scope_id, {})[event.event_id] = updated
        return updated

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


def test_chat_workflow_service_versions_config_writes_and_rejects_stale_updates() -> None:
    repo = _WorkflowRepo()
    service = ChatWorkflowService(repo)

    created = service.set_workflow(
        "chat-1",
        kind="cel-group",
        state="active",
        config={"participants": []},
    )
    updated = service.set_workflow(
        "chat-1",
        kind="cel-group",
        state="active",
        config={"participants": [{"handle": "worker-a"}]},
        expected_state_version=created["state_version"],
    )

    assert created["state_version"] == 0
    assert updated["state_version"] == 1
    try:
        service.set_workflow(
            "chat-1",
            kind="cel-group",
            state="active",
            config={"participants": [{"handle": "worker-b"}]},
            expected_state_version=created["state_version"],
        )
    except StaleChatWorkflowVersionError as exc:
        assert exc.chat_id == "chat-1"
        assert exc.expected_state_version == 0
        assert exc.actual_state_version == 1
    else:
        raise AssertionError("stale workflow config write did not fail")

    assert service.get_workflow("chat-1") == updated


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


def test_chat_workflow_event_service_versions_updates_and_rejects_stale_writes() -> None:
    repo = _WorkflowEventRepo()
    service = ChatWorkflowEventService(repo)

    event = service.create_event("chat-1", kind="task_proposed_review")
    updated = service.update_event(
        "chat-1",
        event["event_id"],
        decision_states={"reviewer-a": {"1": "completed"}},
        expected_state_version=event["state_version"],
    )

    assert event["state_version"] == 0
    assert updated is not None
    assert updated["state_version"] == 1
    try:
        service.update_event(
            "chat-1",
            event["event_id"],
            decision_states={"reviewer-b": {"1": "pending"}},
            expected_state_version=event["state_version"],
        )
    except StaleChatWorkflowEventVersionError as exc:
        assert exc.chat_id == "chat-1"
        assert exc.event_id == event["event_id"]
        assert exc.expected_state_version == 0
        assert exc.actual_state_version == 1
    else:
        raise AssertionError("stale workflow event write did not fail")

    assert service.get_event("chat-1", event["event_id"]) == updated


def test_chat_workflow_event_service_emits_change_after_create_when_wired() -> None:
    repo = _WorkflowEventRepo()
    changes = []
    service = ChatWorkflowEventService(repo)
    service.set_event_change_fn(changes.append)

    event = service.create_event(
        "chat-1",
        kind="task_proposed_review",
        requested_by_user_id="owner-1",
    )

    assert len(changes) == 1
    assert changes[0].operation == "created"
    assert changes[0].event == event
    assert changes[0].actor_user_id == "owner-1"


def test_chat_workflow_event_service_requires_requester_for_wired_change() -> None:
    repo = _WorkflowEventRepo()
    service = ChatWorkflowEventService(repo)
    service.set_event_change_fn(lambda _change: None)

    try:
        service.create_event("chat-1", kind="task_proposed_review")
    except RuntimeError as exc:
        assert str(exc) == "Workflow event change requires requested_by_user_id"
    else:
        raise AssertionError("wired workflow event change accepted missing requester")
    assert repo.list_all("chat-1") == []


def test_chat_workflow_event_service_emits_change_after_update_when_wired() -> None:
    repo = _WorkflowEventRepo()
    changes = []
    service = ChatWorkflowEventService(repo)
    event = service.create_event("chat-1", kind="task_proposed_review")
    service.set_event_change_fn(changes.append)

    updated = service.update_event(
        "chat-1",
        event["event_id"],
        state="settled",
        updated_by_user_id="reviewer-1",
    )

    assert len(changes) == 1
    assert changes[0].operation == "updated"
    assert changes[0].event == updated
    assert changes[0].actor_user_id == "reviewer-1"


def test_chat_workflow_event_service_requires_actor_for_wired_update_change() -> None:
    repo = _WorkflowEventRepo()
    service = ChatWorkflowEventService(repo)
    event = service.create_event("chat-1", kind="task_proposed_review")
    service.set_event_change_fn(lambda _change: None)

    try:
        service.update_event("chat-1", event["event_id"], state="settled")
    except RuntimeError as exc:
        assert str(exc) == "Workflow event change requires updated_by_user_id"
    else:
        raise AssertionError("wired workflow event change accepted missing actor")
    assert service.get_event("chat-1", event["event_id"]) == event
