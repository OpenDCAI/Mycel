from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.threads.chat_adapters import chat_inlet as owner_chat_inlet
from backend.threads.chat_adapters.chat_notification_format import format_chat_notification
from backend.threads.chat_adapters.runtime_chat_delivery_action import (
    RuntimeChatDeliveryAction,
    dispatch_runtime_chat_delivery_actions,
    plan_runtime_chat_delivery_envelope,
)
from messaging.delivery.dispatcher import ChatDeliveryRequest


def _hook_app(gateway: object) -> SimpleNamespace:
    default_thread = {"id": "thread-1", "agent_user_id": "agent-user-1", "is_main": True, "branch_index": 0}
    activity_reader = SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: [])
    return SimpleNamespace(
        state=SimpleNamespace(
            threads_runtime_state=SimpleNamespace(
                agent_runtime_gateway=gateway,
                activity_reader=activity_reader,
            ),
            thread_repo=SimpleNamespace(
                get_by_user_id=lambda uid: default_thread if uid == "agent-user-1" else None,
                list_by_agent_user=lambda uid: [default_thread] if uid == "agent-user-1" else [],
            ),
        )
    )


def _runtime_chat_action(**overrides) -> RuntimeChatDeliveryAction:
    values = {
        "chat_id": "chat-1",
        "recipient_id": "agent-user-1",
        "recipient_user_id": "agent-user-1",
        "recipient_user_type": "agent",
        "sender_id": "human-user-1",
        "sender_type": "human",
        "sender_name": "Human",
        "sender_avatar_url": None,
        "content": "rendered chat reminder",
        "raw_content": "raw chat message",
        "signal": None,
    }
    values.update(overrides)
    return RuntimeChatDeliveryAction(**values)


def test_chat_delivery_request_builds_runtime_action() -> None:
    action = owner_chat_inlet.chat_delivery_runtime_action(
        ChatDeliveryRequest(
            recipient_id="agent-user-1",
            recipient_user=SimpleNamespace(id="agent-user-1", type="agent"),
            content="hello",
            sender_name="Human",
            sender_type="human",
            chat_id="chat-1",
            sender_id="human-user-1",
            sender_avatar_url=None,
            unread_count=3,
            signal=None,
        )
    )

    assert action == RuntimeChatDeliveryAction(
        chat_id="chat-1",
        recipient_id="agent-user-1",
        recipient_user_id="agent-user-1",
        recipient_user_type="agent",
        sender_id="human-user-1",
        sender_type="human",
        sender_name="Human",
        sender_avatar_url=None,
        content=format_chat_notification("Human", "chat-1", 3, signal=None),
        raw_content="hello",
        signal=None,
    )


def test_chat_delivery_action_planner_returns_runtime_action() -> None:
    planner = owner_chat_inlet.chat_delivery_runtime_action_planner()

    actions = planner(
        ChatDeliveryRequest(
            recipient_id="agent-user-1",
            recipient_user=SimpleNamespace(id="agent-user-1", type="agent"),
            content="hello",
            sender_name="Human",
            sender_type="human",
            chat_id="chat-1",
            sender_id="human-user-1",
            sender_avatar_url=None,
            unread_count=2,
            signal=None,
        )
    )

    assert len(actions) == 1
    assert actions[0].recipient_user_id == "agent-user-1"
    assert actions[0].content == format_chat_notification("Human", "chat-1", 2, signal=None)
    assert actions[0].raw_content == "hello"


def test_runtime_chat_delivery_action_plans_runtime_envelope() -> None:
    action = _runtime_chat_action(signal="urgent")

    envelope = plan_runtime_chat_delivery_envelope(
        action,
        thread_repo=_hook_app(object()).state.thread_repo,
        activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
    )

    assert envelope is not None
    assert envelope.chat.chat_id == "chat-1"
    assert envelope.recipient.agent_user_id == "agent-user-1"
    assert envelope.recipient.thread_id == "thread-1"
    assert envelope.sender.user_id == "human-user-1"
    assert envelope.sender.source == "chat"
    assert envelope.message.content == "rendered chat reminder"
    assert envelope.message.signal == "urgent"
    assert envelope.extensions == {
        "mycel": {
            "recipient_user_id": "agent-user-1",
            "recipient_user_type": "agent",
            "raw_content": "raw chat message",
        }
    }


@pytest.mark.asyncio
async def test_runtime_chat_delivery_actions_dispatches_prior_envelopes_before_later_planning_failure() -> None:
    class RecordingGateway:
        def __init__(self) -> None:
            self.envelopes = []

        async def dispatch_chat(self, envelope):
            self.envelopes.append(envelope)

    gateway = RecordingGateway()

    with pytest.raises(RuntimeError, match="Managed agent runtime is unavailable for chat delivery to agent-user-1"):
        await dispatch_runtime_chat_delivery_actions(
            _hook_app(gateway),
            [
                _runtime_chat_action(
                    recipient_id="external-user-1",
                    recipient_user_id="external-user-1",
                    recipient_user_type="external",
                    content="external reminder",
                    raw_content="raw external",
                ),
                _runtime_chat_action(
                    content="agent reminder",
                    raw_content="raw agent",
                ),
            ],
            thread_repo=object(),
            activity_reader=None,
        )

    assert [envelope.recipient.agent_user_id for envelope in gateway.envelopes] == ["external-user-1"]


@pytest.mark.asyncio
async def test_chat_delivery_hook_propagates_runtime_gateway_failures() -> None:
    class FailingGateway:
        async def dispatch_chat(self, _envelope):
            raise RuntimeError("runtime gateway down")

    app = _hook_app(FailingGateway())
    deliver = owner_chat_inlet.make_chat_delivery_fn(
        app,
        activity_reader=app.state.threads_runtime_state.activity_reader,
        thread_repo=app.state.thread_repo,
    )
    request = ChatDeliveryRequest(
        recipient_id="agent-user-1",
        recipient_user=SimpleNamespace(id="agent-user-1", type="agent"),
        content="hello",
        sender_name="Human",
        sender_type="human",
        chat_id="chat-1",
        sender_id="human-user-1",
        sender_avatar_url=None,
        unread_count=0,
        signal=None,
    )

    with pytest.raises(RuntimeError, match="runtime gateway down"):
        await asyncio.to_thread(deliver, request)


@pytest.mark.asyncio
async def test_chat_delivery_event_and_hook_use_request_sender_type() -> None:
    class RecordingGateway:
        envelope = None

        async def dispatch_chat(self, envelope):
            self.envelope = envelope

    gateway = RecordingGateway()
    app = _hook_app(gateway)
    deliver = owner_chat_inlet.make_chat_delivery_fn(
        app,
        activity_reader=app.state.threads_runtime_state.activity_reader,
        thread_repo=app.state.thread_repo,
    )
    request = ChatDeliveryRequest(
        recipient_id="agent-user-1",
        recipient_user=SimpleNamespace(id="agent-user-1", type="agent"),
        content="hello",
        sender_name="Human",
        sender_type="human",
        chat_id="chat-1",
        sender_id="human-user-1",
        sender_avatar_url=None,
        unread_count=3,
        signal=None,
    )

    await asyncio.to_thread(deliver, request)

    assert gateway.envelope is not None
    assert gateway.envelope.sender.user_type == "human"
    assert "New message from Human in chat chat-1 (3 unread)." in gateway.envelope.message.content
    assert 'read_messages(chat_id="chat-1")' in gateway.envelope.message.content
    assert gateway.envelope.extensions["mycel"]["raw_content"] == "hello"


@pytest.mark.asyncio
async def test_chat_delivery_hook_skips_agent_wake_when_no_runtime_thread() -> None:
    class RecordingGateway:
        called = False

        async def dispatch_chat(self, _envelope):
            self.called = True

    gateway = RecordingGateway()
    app = SimpleNamespace(
        state=SimpleNamespace(
            threads_runtime_state=SimpleNamespace(agent_runtime_gateway=gateway),
            thread_repo=SimpleNamespace(get_by_user_id=lambda _uid: None, list_by_agent_user=lambda _uid: []),
        )
    )
    deliver = owner_chat_inlet.make_chat_delivery_fn(
        app,
        activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
        thread_repo=app.state.thread_repo,
    )
    request = ChatDeliveryRequest(
        recipient_id="agent-user-1",
        recipient_user=SimpleNamespace(id="agent-user-1", type="agent"),
        content="hello",
        sender_name="Human",
        sender_type="human",
        chat_id="chat-1",
        sender_id="human-user-1",
        sender_avatar_url=None,
        unread_count=3,
        signal=None,
    )

    await asyncio.to_thread(deliver, request)

    assert gateway.called is False


@pytest.mark.asyncio
async def test_chat_delivery_actions_skip_without_borrowing_gateway_when_no_runtime_thread() -> None:
    app_without_gateway = SimpleNamespace(state=SimpleNamespace())
    thread_repo = SimpleNamespace(get_by_user_id=lambda _uid: None, list_by_agent_user=lambda _uid: [])

    dispatched_count = await dispatch_runtime_chat_delivery_actions(
        app_without_gateway,
        [_runtime_chat_action()],
        thread_repo=thread_repo,
        activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
    )

    assert dispatched_count == 0


@pytest.mark.asyncio
async def test_chat_delivery_hook_routes_external_user_to_external_runtime_without_thread() -> None:
    class RecordingGateway:
        envelope = None

        async def dispatch_chat(self, envelope):
            self.envelope = envelope

    gateway = RecordingGateway()
    app = _hook_app(gateway)
    deliver = owner_chat_inlet.make_chat_delivery_fn(
        app,
        activity_reader=app.state.threads_runtime_state.activity_reader,
        thread_repo=app.state.thread_repo,
    )
    request = ChatDeliveryRequest(
        recipient_id="external-user-1",
        recipient_user=SimpleNamespace(id="external-user-1", type="external"),
        content="hello",
        sender_name="Human",
        sender_type="human",
        chat_id="chat-1",
        sender_id="human-user-1",
        sender_avatar_url=None,
        unread_count=4,
        signal=None,
    )

    await asyncio.to_thread(deliver, request)

    assert gateway.envelope is not None
    assert gateway.envelope.recipient.agent_user_id == "external-user-1"
    assert gateway.envelope.recipient.runtime_source == "external"
    assert gateway.envelope.recipient.thread_id is None
    assert "New message from Human in chat chat-1 (4 unread)." in gateway.envelope.message.content
    assert gateway.envelope.extensions["mycel"]["raw_content"] == "hello"


@pytest.mark.asyncio
async def test_chat_delivery_hook_requires_recipient_user_type() -> None:
    class RecordingGateway:
        called = False

        async def dispatch_chat(self, _envelope):
            self.called = True

    gateway = RecordingGateway()
    app = _hook_app(gateway)
    deliver = owner_chat_inlet.make_chat_delivery_fn(
        app,
        activity_reader=app.state.threads_runtime_state.activity_reader,
        thread_repo=app.state.thread_repo,
    )
    request = ChatDeliveryRequest(
        recipient_id="agent-user-1",
        recipient_user=SimpleNamespace(id="agent-user-1"),
        content="hello",
        sender_name="Human",
        sender_type="human",
        chat_id="chat-1",
        sender_id="human-user-1",
        sender_avatar_url=None,
        unread_count=0,
        signal=None,
    )

    with pytest.raises(RuntimeError, match="Chat delivery recipient is missing user type: agent-user-1"):
        await asyncio.to_thread(deliver, request)

    assert gateway.called is False


@pytest.mark.asyncio
async def test_chat_delivery_hook_requires_recipient_user_id() -> None:
    class RecordingGateway:
        called = False

        async def dispatch_chat(self, _envelope):
            self.called = True

    gateway = RecordingGateway()
    app = _hook_app(gateway)
    deliver = owner_chat_inlet.make_chat_delivery_fn(
        app,
        activity_reader=app.state.threads_runtime_state.activity_reader,
        thread_repo=app.state.thread_repo,
    )
    request = ChatDeliveryRequest(
        recipient_id="agent-user-1",
        recipient_user=SimpleNamespace(type="agent"),
        content="hello",
        sender_name="Human",
        sender_type="human",
        chat_id="chat-1",
        sender_id="human-user-1",
        sender_avatar_url=None,
        unread_count=0,
        signal=None,
    )

    with pytest.raises(RuntimeError, match="Chat delivery recipient is missing user id: agent-user-1"):
        await asyncio.to_thread(deliver, request)

    assert gateway.called is False


@pytest.mark.asyncio
async def test_chat_delivery_hook_routes_external_user_without_managed_activity_reader() -> None:
    class RecordingGateway:
        envelope = None

        async def dispatch_chat(self, envelope):
            self.envelope = envelope

    gateway = RecordingGateway()
    app = SimpleNamespace(state=SimpleNamespace(threads_runtime_state=SimpleNamespace(agent_runtime_gateway=gateway)))
    deliver = owner_chat_inlet.make_chat_delivery_fn(
        app,
        activity_reader=None,
        thread_repo=object(),
    )
    request = ChatDeliveryRequest(
        recipient_id="external-user-1",
        recipient_user=SimpleNamespace(id="external-user-1", type="external"),
        content="hello",
        sender_name="Human",
        sender_type="human",
        chat_id="chat-1",
        sender_id="human-user-1",
        sender_avatar_url=None,
        unread_count=2,
        signal=None,
    )

    await asyncio.to_thread(deliver, request)

    assert gateway.envelope is not None
    assert gateway.envelope.recipient.agent_user_id == "external-user-1"
    assert gateway.envelope.recipient.runtime_source == "external"
    assert gateway.envelope.recipient.thread_id is None


@pytest.mark.asyncio
async def test_chat_delivery_hook_fails_loudly_for_managed_agent_without_activity_reader() -> None:
    class RecordingGateway:
        called = False

        async def dispatch_chat(self, _envelope):
            self.called = True

    gateway = RecordingGateway()
    app = SimpleNamespace(state=SimpleNamespace(threads_runtime_state=SimpleNamespace(agent_runtime_gateway=gateway)))
    deliver = owner_chat_inlet.make_chat_delivery_fn(
        app,
        activity_reader=None,
        thread_repo=object(),
    )
    request = ChatDeliveryRequest(
        recipient_id="agent-user-1",
        recipient_user=SimpleNamespace(id="agent-user-1", type="agent"),
        content="hello",
        sender_name="Human",
        sender_type="human",
        chat_id="chat-1",
        sender_id="human-user-1",
        sender_avatar_url=None,
        unread_count=2,
        signal=None,
    )

    with pytest.raises(RuntimeError, match="Managed agent runtime is unavailable for chat delivery to agent-user-1"):
        await asyncio.to_thread(deliver, request)

    assert gateway.called is False
