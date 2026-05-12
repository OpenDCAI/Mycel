from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Literal

import pytest

from backend.threads.chat_adapters.workflow_event_inlet import (
    make_workflow_event_notification_actions,
    make_workflow_event_notification_fn,
    workflow_event_runtime_notification_action,
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


def test_workflow_event_notification_action_is_metadata_only() -> None:
    action = workflow_event_runtime_notification_action(
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
        recipient_user_id="agent-1",
    )

    assert action.event_type == "chat.workflow.event"
    assert action.notification_type == "workflow_event"
    assert action.recipient_user_id == "agent-1"
    assert action.sender_user_id == "owner-1"
    assert action.content == "Workflow event task_proposed_review was created and is open."
    assert action.metadata == {
        "chat_id": "chat-1",
        "event_id": "event-1",
        "kind": "task_proposed_review",
        "operation": "created",
        "actor_user_id": "owner-1",
        "resource_refs": [{"type": "task", "id": "1"}],
        "state": "open",
        "state_version": 3,
    }
    assert action.transport.delivery_id == "workflow:chat-1:event-1:3"
    assert action.transport.correlation_id == "workflow:chat-1:event-1"
    assert action.transport.idempotency_key == "workflow:chat-1:event-1:3"
    assert "must not leak" not in str(action)


def test_workflow_event_notification_fails_loudly_on_missing_identity() -> None:
    try:
        workflow_event_runtime_notification_action(
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
            recipient_user_id="agent-1",
        )
    except RuntimeError as exc:
        assert str(exc) == "Workflow event notification is missing event_id"
    else:
        raise AssertionError("missing workflow event identity did not fail")


def test_workflow_event_notification_planner_selects_recipient_actions() -> None:
    members = [
        {"user_id": "owner-1"},
        {"user_id": "agent-1"},
        {"user_id": "agent-without-thread"},
        {"user_id": "external-1"},
        {"user_id": "human-2"},
    ]

    actions = make_workflow_event_notification_actions(
        _change("updated"),
        members,
    )

    assert [action.recipient_user_id for action in actions] == ["agent-1", "agent-without-thread", "external-1", "human-2"]
    assert all(action.sender_user_id == "owner-1" for action in actions)
    for action in actions:
        assert action.metadata is not None
        assert action.metadata["event_id"] == "event-1"
        assert action.metadata["operation"] == "updated"


@pytest.mark.asyncio
async def test_workflow_event_notification_fn_selects_runtime_members() -> None:
    gateway = _RecordingGateway()
    messaging_service = SimpleNamespace(
        list_chat_members=lambda _chat_id: [
            {"user_id": "owner-1"},
            {"user_id": "agent-1"},
            {"user_id": "agent-without-thread"},
            {"user_id": "external-1"},
            {"user_id": "human-2"},
        ]
    )
    notify = make_workflow_event_notification_fn(
        _runtime_app(gateway),
        activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
        thread_repo=_thread_repo("agent-1"),
        user_repo=_users("agent-1", "agent-without-thread"),
        messaging_service=messaging_service,
    )

    await asyncio.to_thread(notify, _change("updated"))

    envelopes = gateway.envelopes
    assert [envelope.recipient.agent_user_id for envelope in envelopes] == ["agent-1", "external-1"]
    assert [envelope.recipient.runtime_source for envelope in envelopes] == ["mycel", "external"]
    assert envelopes[0].recipient.thread_id == "thread-agent-1"
    assert all(envelope.sender.user_id == "owner-1" for envelope in envelopes)
    for envelope in envelopes:
        assert envelope.message.metadata is not None
        assert envelope.message.metadata["event_id"] == "event-1"
        assert envelope.message.metadata["operation"] == "updated"


@pytest.mark.asyncio
async def test_workflow_event_notification_fn_keeps_identity_context() -> None:
    gateway = _RecordingGateway()
    messaging_service = SimpleNamespace(list_chat_members=lambda _chat_id: [{"user_id": "missing-recipient"}])
    notify = make_workflow_event_notification_fn(
        _runtime_app(gateway),
        activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
        thread_repo=_thread_repo("agent-1"),
        user_repo=_users("agent-1"),
        messaging_service=messaging_service,
    )

    try:
        await asyncio.to_thread(notify, _change("updated"))
    except RuntimeError as exc:
        assert str(exc) == "Workflow event notification recipient user not found: missing-recipient"
    else:
        raise AssertionError("missing workflow event recipient did not fail")


@pytest.mark.asyncio
async def test_workflow_event_notification_fn_skips_gateway_when_no_runtime_recipients() -> None:
    messaging_service = SimpleNamespace(list_chat_members=lambda _chat_id: [{"user_id": "owner-1"}, {"user_id": "human-2"}])
    notify = make_workflow_event_notification_fn(
        SimpleNamespace(state=SimpleNamespace(threads_runtime_state=SimpleNamespace())),
        activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
        thread_repo=_thread_repo(),
        user_repo=_users(),
        messaging_service=messaging_service,
    )

    await asyncio.to_thread(notify, _change("updated"))


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
