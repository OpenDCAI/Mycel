from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from backend.threads.chat_adapters.runtime_notification_action import (
    RuntimeNotificationAction,
    dispatch_runtime_notification_actions,
    make_runtime_notification_event_hook,
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


class _RecordingGateway:
    def __init__(self) -> None:
        self.envelopes = []

    async def dispatch_notification(self, envelope):
        self.envelopes.append(envelope)
        return SimpleNamespace(status="accepted", thread_id=envelope.recipient.thread_id)


def _activity_reader() -> SimpleNamespace:
    return SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: [])


def _action(**overrides) -> RuntimeNotificationAction:
    payload: dict[str, Any] = {
        "context": "Test action",
        "recipient_user_id": "agent-1",
        "sender_user_id": "owner-1",
        "sender_source": "workflow",
        "event_type": "test.event",
        "notification_type": "test",
        "content": "Action happened.",
    }
    payload.update(overrides)
    return RuntimeNotificationAction(**payload)


@pytest.mark.asyncio
async def test_runtime_notification_action_resolves_and_dispatches_to_runtime_recipient() -> None:
    gateway = _RecordingGateway()

    dispatched_count = await dispatch_runtime_notification_actions(
        _runtime_app(gateway),
        [
            _action(
                metadata={"resource_id": "resource-1"},
                transport=AgentRuntimeTransport(
                    delivery_id="delivery-1",
                    correlation_id="resource-1",
                    idempotency_key="delivery-1",
                ),
            ),
        ],
        user_repo=_users(),
        thread_repo=_thread_repo(),
        activity_reader=_activity_reader(),
    )

    assert dispatched_count == 1
    assert len(gateway.envelopes) == 1
    envelope = gateway.envelopes[0]
    assert envelope.recipient.agent_user_id == "agent-1"
    assert envelope.recipient.runtime_source == "mycel"
    assert envelope.recipient.thread_id == "thread-agent-1"
    assert envelope.sender.user_id == "owner-1"
    assert envelope.sender.source == "workflow"
    assert envelope.event_type == "test.event"
    assert envelope.notification_type == "test"
    assert envelope.message.content == "Action happened."
    assert envelope.message.metadata == {"resource_id": "resource-1"}
    assert envelope.transport.delivery_id == "delivery-1"


@pytest.mark.asyncio
async def test_runtime_notification_actions_dispatches_only_runtime_recipients() -> None:
    gateway = _RecordingGateway()

    dispatched_count = await dispatch_runtime_notification_actions(
        _runtime_app(gateway),
        [
            _action(),
            _action(
                recipient_user_id="owner-1",
            ),
        ],
        user_repo=_users(),
        thread_repo=_thread_repo(),
        activity_reader=_activity_reader(),
    )

    assert dispatched_count == 1
    assert [envelope.recipient.agent_user_id for envelope in gateway.envelopes] == ["agent-1"]


@pytest.mark.asyncio
async def test_runtime_notification_hook_plans_and_dispatches_actions() -> None:
    gateway = _RecordingGateway()

    def planner(value: str) -> list[RuntimeNotificationAction]:
        return [_action(context="Test hook", content=f"Action {value}.")]

    hook = make_runtime_notification_event_hook(
        _runtime_app(gateway),
        planner,
        user_repo=_users(),
        thread_repo=_thread_repo(),
        activity_reader=_activity_reader(),
    )

    await asyncio.to_thread(hook, "event-2")

    assert [envelope.message.content for envelope in gateway.envelopes] == ["Action event-2."]
