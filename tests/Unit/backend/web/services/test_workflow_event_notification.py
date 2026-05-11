from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.threads.chat_adapters.workflow_event_inlet import (
    dispatch_workflow_event_notification,
    make_workflow_event_notification_envelope,
)
from protocols.agent_runtime import AgentChatRecipient, AgentRuntimeActor


def test_workflow_event_notification_is_metadata_only() -> None:
    envelope = make_workflow_event_notification_envelope(
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
        recipient=AgentChatRecipient(agent_user_id="agent-1", runtime_source="mycel", thread_id="thread-1"),
        sender=AgentRuntimeActor(user_id="owner-1", user_type="human", display_name="Owner", source="workflow"),
    )

    assert envelope.event_type == "chat.workflow.event"
    assert envelope.notification_type == "workflow_event"
    assert envelope.recipient.agent_user_id == "agent-1"
    assert envelope.sender.user_id == "owner-1"
    assert envelope.message.content == "Workflow event task_proposed_review is open."
    assert envelope.message.metadata == {
        "chat_id": "chat-1",
        "event_id": "event-1",
        "kind": "task_proposed_review",
        "state": "open",
        "state_version": 3,
    }
    assert envelope.transport.delivery_id == "workflow:chat-1:event-1:3"
    assert envelope.transport.correlation_id == "workflow:chat-1:event-1"
    assert envelope.transport.idempotency_key == "workflow:chat-1:event-1:3"
    assert "must not leak" not in str(envelope)


def test_workflow_event_notification_fails_loudly_on_missing_identity() -> None:
    try:
        make_workflow_event_notification_envelope(
            event={
                "chat_id": "chat-1",
                "event_id": "",
                "kind": "task_proposed_review",
                "state": "open",
                "state_version": 3,
            },
            recipient=AgentChatRecipient(agent_user_id="agent-1", runtime_source="mycel", thread_id="thread-1"),
            sender=AgentRuntimeActor(user_id="owner-1", user_type="human", display_name="Owner", source="workflow"),
        )
    except RuntimeError as exc:
        assert str(exc) == "Workflow event notification is missing event_id"
    else:
        raise AssertionError("missing workflow event identity did not fail")


@pytest.mark.asyncio
async def test_dispatch_workflow_event_notification_uses_runtime_gateway() -> None:
    class RecordingGateway:
        envelope = None

        async def dispatch_notification(self, envelope):
            self.envelope = envelope
            return SimpleNamespace(status="accepted", thread_id=envelope.recipient.thread_id)

    gateway = RecordingGateway()
    app = SimpleNamespace(state=SimpleNamespace(threads_runtime_state=SimpleNamespace(agent_runtime_gateway=gateway)))

    await dispatch_workflow_event_notification(
        app,
        event={
            "chat_id": "chat-1",
            "event_id": "event-1",
            "kind": "task_proposed_review",
            "state": "open",
            "state_version": 3,
        },
        recipient=AgentChatRecipient(agent_user_id="agent-1", runtime_source="mycel", thread_id="thread-1"),
        sender=AgentRuntimeActor(user_id="owner-1", user_type="human", display_name="Owner", source="workflow"),
    )

    assert gateway.envelope is not None
    assert gateway.envelope.event_type == "chat.workflow.event"
    assert gateway.envelope.message.metadata["event_id"] == "event-1"
