from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Literal

import pytest

from backend.threads.chat_adapters.workflow_event_inlet import (
    dispatch_workflow_event_notifications,
    make_workflow_event_notification_fn,
    plan_workflow_event_runtime_notifications,
)
from core.work_item.chat_workflow.service import WorkflowEventChange


def _event() -> dict[str, object]:
    return {
        "chat_id": "chat-1",
        "event_id": "event-1",
        "kind": "task_proposed_review",
        "state": "open",
        "state_version": 3,
        "resource_refs": [{"type": "task", "id": "task-1"}],
    }


def _change(operation: Literal["created", "updated"] = "created") -> WorkflowEventChange:
    return WorkflowEventChange(
        operation=operation,
        event=_event(),
        actor_user_id="owner-1",
    )


class _RecordingGateway:
    def __init__(self) -> None:
        self.envelopes = []

    async def dispatch_notification(self, envelope):
        self.envelopes.append(envelope)
        return SimpleNamespace(status="accepted", thread_id=envelope.recipient.thread_id)


def _runtime_app(gateway: _RecordingGateway) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(threads_runtime_state=SimpleNamespace(agent_runtime_gateway=gateway)))


def _users(*agent_ids: str):
    rows = {
        "owner-1": SimpleNamespace(id="owner-1", type="human", display_name="Owner"),
        "external-1": SimpleNamespace(id="external-1", type="external", display_name="External"),
        "human-2": SimpleNamespace(id="human-2", type="human", display_name="Human"),
    }
    rows.update({agent_id: SimpleNamespace(id=agent_id, type="agent", display_name=agent_id) for agent_id in agent_ids})
    return SimpleNamespace(get_by_id=lambda uid: rows.get(uid))


def _thread_repo(*agent_ids: str) -> SimpleNamespace:
    def _thread(uid: str) -> dict[str, object] | None:
        if uid in agent_ids:
            return {"id": f"thread-{uid}", "agent_user_id": uid, "is_main": True, "branch_index": 0}
        return None

    return SimpleNamespace(
        get_by_user_id=_thread,
        list_by_agent_user=lambda uid: [_thread(uid)] if _thread(uid) is not None else [],
    )


def test_workflow_event_notification_is_metadata_only() -> None:
    envelopes = plan_workflow_event_runtime_notifications(
        change=WorkflowEventChange(
            operation="created",
            event={
                "chat_id": "chat-1",
                "event_id": "event-1",
                "kind": "task_proposed_review",
                "state": "open",
                "state_version": 3,
                "resource_refs": [{"type": "task", "id": "1"}],
                "rationales": {"reviewer-1": "must not leak"},
                "final_state": {"1": "completed"},
            },
            actor_user_id="owner-1",
        ),
        members=[{"user_id": "agent-1"}],
        user_repo=_users("agent-1"),
        thread_repo=_thread_repo("agent-1"),
        activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
    )

    assert len(envelopes) == 1
    envelope = envelopes[0]
    assert envelope.event_type == "chat.workflow.event"
    assert envelope.notification_type == "workflow_event"
    assert envelope.recipient.agent_user_id == "agent-1"
    assert envelope.recipient.thread_id == "thread-agent-1"
    assert envelope.sender.user_id == "owner-1"
    assert envelope.message.content == "Workflow event task_proposed_review was created and is open."
    assert envelope.message.metadata == {
        "chat_id": "chat-1",
        "event_id": "event-1",
        "kind": "task_proposed_review",
        "operation": "created",
        "actor_user_id": "owner-1",
        "resource_refs": [{"type": "task", "id": "1"}],
        "state": "open",
        "state_version": 3,
    }
    assert envelope.transport.delivery_id == "workflow:chat-1:event-1:3"
    assert envelope.transport.correlation_id == "workflow:chat-1:event-1"
    assert envelope.transport.idempotency_key == "workflow:chat-1:event-1:3"
    assert "must not leak" not in str(envelope)


def test_workflow_event_notification_fails_loudly_on_missing_identity() -> None:
    try:
        plan_workflow_event_runtime_notifications(
            change=WorkflowEventChange(
                operation="created",
                event={
                    "chat_id": "chat-1",
                    "event_id": "",
                    "kind": "task_proposed_review",
                    "state": "open",
                    "state_version": 3,
                },
                actor_user_id="owner-1",
            ),
            members=[{"user_id": "agent-1"}],
            user_repo=_users("agent-1"),
            thread_repo=_thread_repo("agent-1"),
            activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
        )
    except RuntimeError as exc:
        assert str(exc) == "Workflow event notification is missing event_id"
    else:
        raise AssertionError("missing workflow event identity did not fail")


def test_workflow_event_notification_planner_selects_runtime_members() -> None:
    envelopes = plan_workflow_event_runtime_notifications(
        change=_change("updated"),
        members=[
            {"user_id": "owner-1"},
            {"user_id": "agent-1"},
            {"user_id": "agent-without-thread"},
            {"user_id": "external-1"},
            {"user_id": "human-2"},
        ],
        user_repo=_users("agent-1", "agent-without-thread"),
        thread_repo=_thread_repo("agent-1"),
        activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
    )

    assert [envelope.recipient.agent_user_id for envelope in envelopes] == ["agent-1", "external-1"]
    assert [envelope.recipient.runtime_source for envelope in envelopes] == ["mycel", "external"]
    assert envelopes[0].recipient.thread_id == "thread-agent-1"
    assert all(envelope.sender.user_id == "owner-1" for envelope in envelopes)
    for envelope in envelopes:
        assert envelope.message.metadata is not None
        assert envelope.message.metadata["event_id"] == "event-1"
        assert envelope.message.metadata["operation"] == "updated"


def test_workflow_event_notification_planner_keeps_identity_context() -> None:
    try:
        plan_workflow_event_runtime_notifications(
            change=_change("updated"),
            members=[{"user_id": "missing-recipient"}],
            user_repo=_users("agent-1"),
            thread_repo=_thread_repo("agent-1"),
            activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
        )
    except RuntimeError as exc:
        assert str(exc) == "Workflow event notification recipient user not found: missing-recipient"
    else:
        raise AssertionError("missing workflow event recipient did not fail")


@pytest.mark.asyncio
async def test_dispatch_workflow_event_notifications_executes_planned_envelopes() -> None:
    gateway = _RecordingGateway()

    await dispatch_workflow_event_notifications(
        _runtime_app(gateway),
        change=_change(),
        members=[{"user_id": "owner-1"}, {"user_id": "agent-1"}],
        user_repo=_users("agent-1"),
        thread_repo=_thread_repo("agent-1"),
        activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
    )

    assert [envelope.recipient.agent_user_id for envelope in gateway.envelopes] == ["agent-1"]


@pytest.mark.asyncio
async def test_workflow_event_notification_fn_reads_members_and_schedules_runtime_delivery() -> None:
    gateway = _RecordingGateway()
    messaging_service = SimpleNamespace(list_chat_members=lambda chat_id: [{"user_id": "owner-1"}, {"user_id": "agent-1"}])
    notify = make_workflow_event_notification_fn(
        _runtime_app(gateway),
        activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
        thread_repo=_thread_repo("agent-1"),
        user_repo=_users("agent-1"),
        messaging_service=messaging_service,
    )

    await asyncio.to_thread(
        notify,
        _change(),
    )

    assert [envelope.recipient.agent_user_id for envelope in gateway.envelopes] == ["agent-1"]
    assert gateway.envelopes[0].transport.delivery_id == "workflow:chat-1:event-1:3"
