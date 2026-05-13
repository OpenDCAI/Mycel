from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.threads.chat_adapters.runtime_action import dispatch_runtime_action, dispatch_runtime_actions
from backend.threads.chat_adapters.runtime_notification_action import RuntimeNotificationAction
from backend.threads.chat_adapters.runtime_thread_input_action import owner_runtime_thread_input_action
from protocols.agent_runtime import AgentRuntimeNotificationResult, AgentThreadInputResult


def _runtime_app(gateway: object) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(threads_runtime_state=SimpleNamespace(agent_runtime_gateway=gateway)))


def _users() -> SimpleNamespace:
    rows = {
        "owner-1": SimpleNamespace(id="owner-1", type="human", display_name="Owner", avatar=None),
        "agent-1": SimpleNamespace(id="agent-1", type="agent", display_name="Worker", avatar=None),
    }
    return SimpleNamespace(get_by_id=lambda user_id: rows.get(user_id))


def _thread_repo() -> SimpleNamespace:
    thread = {"id": "thread-agent-1", "agent_user_id": "agent-1", "is_main": True, "branch_index": 0}
    return SimpleNamespace(
        get_by_user_id=lambda user_id: thread if user_id == "agent-1" else None,
        list_by_agent_user=lambda user_id: [thread] if user_id == "agent-1" else [],
    )


def _activity_reader() -> SimpleNamespace:
    return SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: [])


class _RecordingGateway:
    def __init__(self) -> None:
        self.notifications = []
        self.thread_inputs = []

    async def dispatch_notification(self, envelope):
        self.notifications.append(envelope)
        return AgentRuntimeNotificationResult(status="accepted", thread_id=envelope.recipient.thread_id)

    async def dispatch_thread_input(self, envelope):
        self.thread_inputs.append(envelope)
        return AgentThreadInputResult(status="started", routing="direct", thread_id=envelope.thread_id)


@pytest.mark.asyncio
async def test_runtime_action_dispatches_notification_and_thread_input_actions_through_one_boundary() -> None:
    gateway = _RecordingGateway()
    notification = RuntimeNotificationAction(
        context="Runtime action test",
        recipient_user_id="agent-1",
        sender_user_id="owner-1",
        sender_source="workflow",
        event_type="test.event",
        notification_type="test",
        content="Notify worker.",
    )
    thread_input = owner_runtime_thread_input_action(
        thread_id="thread-1",
        user_id="owner-1",
        message="Direct input.",
        attachments=None,
        enable_trajectory=True,
    )

    count = await dispatch_runtime_actions(
        _runtime_app(gateway),
        [notification, thread_input],
        user_repo=_users(),
        thread_repo=_thread_repo(),
        activity_reader=_activity_reader(),
    )

    assert count == 2
    assert gateway.notifications[0].event_type == "test.event"
    assert gateway.thread_inputs[0].thread_id == "thread-1"
    assert gateway.thread_inputs[0].enable_trajectory is True


@pytest.mark.asyncio
async def test_runtime_action_returns_thread_input_result() -> None:
    gateway = _RecordingGateway()

    result = await dispatch_runtime_action(
        _runtime_app(gateway),
        owner_runtime_thread_input_action(
            thread_id="thread-1",
            user_id="owner-1",
            message="Direct input.",
            attachments=None,
            enable_trajectory=False,
        ),
    )

    assert result == AgentThreadInputResult(status="started", routing="direct", thread_id="thread-1")
