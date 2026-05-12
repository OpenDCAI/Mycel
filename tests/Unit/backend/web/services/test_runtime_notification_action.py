from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.threads.chat_adapters.runtime_notification_action import (
    RuntimeNotificationAction,
    dispatch_runtime_notification_action,
)
from protocols.agent_runtime import AgentRuntimeTransport


def _runtime_app(gateway: object) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(threads_runtime_state=SimpleNamespace(agent_runtime_gateway=gateway)))


def _users() -> SimpleNamespace:
    rows = {
        "owner-1": SimpleNamespace(id="owner-1", type="human", display_name="Owner", avatar=None),
        "agent-1": SimpleNamespace(id="agent-1", type="agent", display_name="Worker", avatar=None),
    }
    return SimpleNamespace(get_by_id=lambda uid: rows.get(uid))


def _thread_repo() -> SimpleNamespace:
    thread = {"id": "thread-agent-1", "agent_user_id": "agent-1", "is_main": True, "branch_index": 0}
    return SimpleNamespace(
        get_by_user_id=lambda uid: thread if uid == "agent-1" else None,
        list_by_agent_user=lambda uid: [thread] if uid == "agent-1" else [],
    )


@pytest.mark.asyncio
async def test_runtime_notification_action_resolves_and_dispatches_to_runtime_recipient() -> None:
    class RecordingGateway:
        envelope = None

        async def dispatch_notification(self, envelope):
            self.envelope = envelope
            return SimpleNamespace(status="accepted", thread_id=envelope.recipient.thread_id)

    gateway = RecordingGateway()

    dispatched = await dispatch_runtime_notification_action(
        _runtime_app(gateway),
        RuntimeNotificationAction(
            context="Test action",
            recipient_user_id="agent-1",
            sender_user_id="owner-1",
            sender_source="workflow",
            event_type="test.event",
            notification_type="test",
            content="Action happened.",
            metadata={"resource_id": "resource-1"},
            transport=AgentRuntimeTransport(
                delivery_id="delivery-1",
                correlation_id="resource-1",
                idempotency_key="delivery-1",
            ),
        ),
        user_repo=_users(),
        thread_repo=_thread_repo(),
        activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
    )

    assert dispatched is True
    assert gateway.envelope is not None
    assert gateway.envelope.recipient.agent_user_id == "agent-1"
    assert gateway.envelope.recipient.runtime_source == "mycel"
    assert gateway.envelope.recipient.thread_id == "thread-agent-1"
    assert gateway.envelope.sender.user_id == "owner-1"
    assert gateway.envelope.sender.source == "workflow"
    assert gateway.envelope.event_type == "test.event"
    assert gateway.envelope.notification_type == "test"
    assert gateway.envelope.message.content == "Action happened."
    assert gateway.envelope.message.metadata == {"resource_id": "resource-1"}
    assert gateway.envelope.transport.delivery_id == "delivery-1"
