from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from core.work_item.types import WorkItem
from storage.contracts import ChatWorkflowEventRow


@dataclass(frozen=True)
class WorkflowEventChange:
    operation: Literal["created", "updated"]
    event: dict[str, Any]
    actor_user_id: str


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
        expected_state_version: int | None = None,
    ) -> dict[str, Any]:
        return _workflow_response(
            self._repo.upsert(
                chat_id,
                kind=kind,
                state=state,
                config=config or {},
                updated_by_user_id=updated_by_user_id,
                expected_state_version=expected_state_version,
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
        blocks: list[str] | None = None,
        blocked_by: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = WorkItem(
            id=self._repo.next_id(chat_id),
            subject=subject,
            description=description,
            status=status,
            active_form=active_form,
            owner=owner,
            blocks=blocks or [],
            blocked_by=blocked_by or [],
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
        blocks: list[str] | None = None,
        blocked_by: list[str] | None = None,
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
        if blocks is not None:
            item.blocks = list(blocks)
        if blocked_by is not None:
            item.blocked_by = list(blocked_by)
        if metadata is not None:
            item.metadata = dict(metadata)
        self._repo.update(chat_id, item)
        return _task_response(item)

    def delete_task(self, chat_id: str, task_id: str) -> None:
        self._repo.delete(chat_id, task_id)


class ChatWorkflowEventService:
    def __init__(self, event_repo: Any) -> None:
        self._repo = event_repo
        self._event_change_fn: Callable[[WorkflowEventChange], None] | None = None

    def set_event_change_fn(self, change_fn: Callable[[WorkflowEventChange], None]) -> None:
        self._event_change_fn = change_fn

    def list_events(self, chat_id: str) -> list[dict[str, Any]]:
        return [_event_response(event) for event in self._repo.list_all(chat_id)]

    def get_event(self, chat_id: str, event_id: str) -> dict[str, Any] | None:
        event = self._repo.get(chat_id, event_id)
        return _event_response(event) if event is not None else None

    def create_event(
        self,
        chat_id: str,
        *,
        kind: str,
        resource_refs: list[dict[str, Any]] | None = None,
        requested_by_user_id: str | None = None,
        decision_states: dict[str, dict[str, str]] | None = None,
        rationales: dict[str, Any] | None = None,
        final_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = ChatWorkflowEventRow(
            chat_id=chat_id,
            event_id=self._repo.next_id(chat_id),
            kind=kind,
            state="open",
            resource_refs=resource_refs or [],
            requested_by_user_id=requested_by_user_id,
            decision_states=decision_states or {},
            rationales=rationales or {},
            final_state=final_state or {},
            metadata=metadata or {},
            created_at=time.time(),
        )
        self._repo.insert(chat_id, event)
        response = _event_response(event)
        if self._event_change_fn is not None:
            if requested_by_user_id is None:
                raise RuntimeError("Workflow event change requires requested_by_user_id")
            self._event_change_fn(
                WorkflowEventChange(
                    operation="created",
                    event=response,
                    actor_user_id=requested_by_user_id,
                )
            )
        return response

    def update_event(
        self,
        chat_id: str,
        event_id: str,
        *,
        state: str | None = None,
        decision_states: dict[str, dict[str, str]] | None = None,
        rationales: dict[str, Any] | None = None,
        final_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        settled_at: float | None = None,
        expected_state_version: int | None = None,
        updated_by_user_id: str | None = None,
    ) -> dict[str, Any] | None:
        event = self._repo.get(chat_id, event_id)
        if event is None:
            return None
        event = event.model_copy(deep=True)
        if state is not None:
            event.state = state
        if decision_states is not None:
            event.decision_states = dict(decision_states)
        if rationales is not None:
            event.rationales = dict(rationales)
        if final_state is not None:
            event.final_state = dict(final_state)
        if metadata is not None:
            event.metadata = dict(metadata)
        if settled_at is not None:
            event.settled_at = settled_at
        updated = self._repo.update(chat_id, event, expected_state_version=expected_state_version)
        response = _event_response(updated)
        if self._event_change_fn is not None:
            if updated_by_user_id is None:
                raise RuntimeError("Workflow event change requires updated_by_user_id")
            self._event_change_fn(
                WorkflowEventChange(
                    operation="updated",
                    event=response,
                    actor_user_id=updated_by_user_id,
                )
            )
        return response

    def delete_event(self, chat_id: str, event_id: str) -> None:
        self._repo.delete(chat_id, event_id)


def _workflow_response(row: Any) -> dict[str, Any]:
    return {
        "chat_id": row.chat_id,
        "kind": row.kind,
        "state": row.state,
        "config": dict(row.config),
        "state_version": row.state_version,
        "updated_by_user_id": row.updated_by_user_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _task_response(item: WorkItem) -> dict[str, Any]:
    payload = item.to_detail()
    payload["status"] = item.status.value if hasattr(item.status, "value") else str(item.status)
    return payload


def _event_response(event: ChatWorkflowEventRow) -> dict[str, Any]:
    return {
        "chat_id": event.chat_id,
        "event_id": event.event_id,
        "kind": event.kind,
        "state": event.state,
        "resource_refs": [dict(ref) for ref in event.resource_refs],
        "requested_by_user_id": event.requested_by_user_id,
        "decision_states": {user_id: dict(states) for user_id, states in event.decision_states.items()},
        "rationales": dict(event.rationales),
        "final_state": dict(event.final_state),
        "metadata": dict(event.metadata),
        "state_version": event.state_version,
        "created_at": event.created_at,
        "updated_at": event.updated_at,
        "settled_at": event.settled_at,
    }
