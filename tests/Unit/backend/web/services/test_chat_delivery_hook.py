from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.threads.chat_adapters import chat_inlet as owner_chat_inlet
from backend.threads.chat_adapters.chat_notification_format import format_chat_notification
from messaging.delivery.dispatcher import ChatDeliveryRequest


def _users(**overrides):
    users = {
        "agent-user-1": SimpleNamespace(id="agent-user-1", type="agent", display_name="Agent", avatar=None),
        "external-user-1": SimpleNamespace(id="external-user-1", type="external", display_name="External", avatar=None),
        "human-user-1": SimpleNamespace(id="human-user-1", type="human", display_name="Human", avatar=None),
    }
    users.update(overrides)
    return SimpleNamespace(get_by_id=lambda user_id: users.get(user_id))


def _hook_app(gateway: object, *, user_repo: object | None = None) -> SimpleNamespace:
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
            user_repo=user_repo or _users(),
        )
    )


def _chat_delivery_request(**overrides) -> ChatDeliveryRequest:
    values = {
        "recipient_id": "agent-user-1",
        "recipient_user": SimpleNamespace(id="agent-user-1", type="agent"),
        "content": "hello",
        "sender_name": "Human",
        "sender_type": "human",
        "chat_id": "chat-1",
        "sender_id": "human-user-1",
        "sender_avatar_url": None,
        "unread_count": 3,
        "signal": None,
    }
    values.update(overrides)
    return ChatDeliveryRequest(**values)


def test_chat_delivery_request_plans_runtime_notification_action() -> None:
    [action] = list(owner_chat_inlet.chat_delivery_runtime_notification_actions(_chat_delivery_request(content="hello", signal="urgent")))

    assert action.context == "Chat delivery"
    assert action.event_type == "chat.message"
    assert action.notification_type == "chat"
    assert action.recipient_user_id == "agent-user-1"
    assert action.sender_user_id == "human-user-1"
    assert action.sender_source == "chat"
    assert action.content == format_chat_notification("Human", "chat-1", 3, signal="urgent")
    assert action.signal == "urgent"
    assert action.metadata == {
        "chat_id": "chat-1",
        "recipient_user_id": "agent-user-1",
        "raw_content": "hello",
    }


@pytest.mark.asyncio
async def test_chat_delivery_hook_propagates_runtime_gateway_failures() -> None:
    class FailingGateway:
        async def dispatch_notification(self, _envelope):
            raise RuntimeError("runtime gateway down")

    app = _hook_app(FailingGateway())
    deliver = owner_chat_inlet.make_chat_delivery_fn(
        app,
        activity_reader=app.state.threads_runtime_state.activity_reader,
        thread_repo=app.state.thread_repo,
        user_repo=app.state.user_repo,
    )

    with pytest.raises(RuntimeError, match="runtime gateway down"):
        await asyncio.to_thread(deliver, _chat_delivery_request())


@pytest.mark.asyncio
async def test_chat_delivery_hook_dispatches_runtime_notification() -> None:
    class RecordingGateway:
        envelope = None

        async def dispatch_notification(self, envelope):
            self.envelope = envelope

    gateway = RecordingGateway()
    app = _hook_app(gateway)
    deliver = owner_chat_inlet.make_chat_delivery_fn(
        app,
        activity_reader=app.state.threads_runtime_state.activity_reader,
        thread_repo=app.state.thread_repo,
        user_repo=app.state.user_repo,
    )

    await asyncio.to_thread(deliver, _chat_delivery_request(content="hello", signal="urgent"))

    assert gateway.envelope is not None
    assert gateway.envelope.event_type == "chat.message"
    assert gateway.envelope.notification_type == "chat"
    assert gateway.envelope.recipient.agent_user_id == "agent-user-1"
    assert gateway.envelope.recipient.runtime_source == "mycel"
    assert gateway.envelope.recipient.thread_id == "thread-1"
    assert gateway.envelope.sender.user_id == "human-user-1"
    assert gateway.envelope.sender.source == "chat"
    assert gateway.envelope.message.content == format_chat_notification("Human", "chat-1", 3, signal="urgent")
    assert gateway.envelope.message.signal == "urgent"
    assert gateway.envelope.message.metadata == {
        "chat_id": "chat-1",
        "recipient_user_id": "agent-user-1",
        "raw_content": "hello",
    }


@pytest.mark.asyncio
async def test_chat_delivery_hook_skips_agent_wake_when_no_runtime_thread() -> None:
    class RecordingGateway:
        called = False

        async def dispatch_notification(self, _envelope):
            self.called = True

    gateway = RecordingGateway()
    app = SimpleNamespace(
        state=SimpleNamespace(
            threads_runtime_state=SimpleNamespace(agent_runtime_gateway=gateway),
            thread_repo=SimpleNamespace(get_by_user_id=lambda _uid: None, list_by_agent_user=lambda _uid: []),
            user_repo=_users(),
        )
    )
    deliver = owner_chat_inlet.make_chat_delivery_fn(
        app,
        activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
        thread_repo=app.state.thread_repo,
        user_repo=app.state.user_repo,
    )

    await asyncio.to_thread(deliver, _chat_delivery_request())

    assert gateway.called is False


@pytest.mark.asyncio
async def test_chat_delivery_hook_skips_without_borrowing_gateway_when_no_runtime_thread() -> None:
    app_without_gateway = SimpleNamespace(state=SimpleNamespace(user_repo=_users()))
    thread_repo = SimpleNamespace(get_by_user_id=lambda _uid: None, list_by_agent_user=lambda _uid: [])
    deliver = owner_chat_inlet.make_chat_delivery_fn(
        app_without_gateway,
        activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
        thread_repo=thread_repo,
        user_repo=app_without_gateway.state.user_repo,
    )

    await asyncio.to_thread(deliver, _chat_delivery_request())


@pytest.mark.asyncio
async def test_chat_delivery_hook_routes_external_user_to_external_runtime_without_thread() -> None:
    class RecordingGateway:
        envelope = None

        async def dispatch_notification(self, envelope):
            self.envelope = envelope

    gateway = RecordingGateway()
    app = _hook_app(gateway)
    deliver = owner_chat_inlet.make_chat_delivery_fn(
        app,
        activity_reader=app.state.threads_runtime_state.activity_reader,
        thread_repo=app.state.thread_repo,
        user_repo=app.state.user_repo,
    )

    await asyncio.to_thread(deliver, _chat_delivery_request(recipient_id="external-user-1", unread_count=4))

    assert gateway.envelope is not None
    assert gateway.envelope.recipient.agent_user_id == "external-user-1"
    assert gateway.envelope.recipient.runtime_source == "external"
    assert gateway.envelope.recipient.thread_id is None
    assert "New message from Human in chat chat-1 (4 unread)." in gateway.envelope.message.content
    assert gateway.envelope.message.metadata["raw_content"] == "hello"


@pytest.mark.asyncio
async def test_chat_delivery_hook_requires_sender_user() -> None:
    class RecordingGateway:
        called = False

        async def dispatch_notification(self, _envelope):
            self.called = True

    gateway = RecordingGateway()
    app = _hook_app(gateway, user_repo=_users(**{"human-user-1": None}))
    deliver = owner_chat_inlet.make_chat_delivery_fn(
        app,
        activity_reader=app.state.threads_runtime_state.activity_reader,
        thread_repo=app.state.thread_repo,
        user_repo=app.state.user_repo,
    )

    with pytest.raises(RuntimeError, match="Chat delivery sender user not found: human-user-1"):
        await asyncio.to_thread(deliver, _chat_delivery_request())

    assert gateway.called is False


@pytest.mark.asyncio
async def test_chat_delivery_hook_routes_external_user_without_managed_activity_reader() -> None:
    class RecordingGateway:
        envelope = None

        async def dispatch_notification(self, envelope):
            self.envelope = envelope

    gateway = RecordingGateway()
    app = SimpleNamespace(state=SimpleNamespace(threads_runtime_state=SimpleNamespace(agent_runtime_gateway=gateway), user_repo=_users()))
    deliver = owner_chat_inlet.make_chat_delivery_fn(
        app,
        activity_reader=None,
        thread_repo=object(),
        user_repo=app.state.user_repo,
    )

    await asyncio.to_thread(deliver, _chat_delivery_request(recipient_id="external-user-1", unread_count=2))

    assert gateway.envelope is not None
    assert gateway.envelope.recipient.agent_user_id == "external-user-1"
    assert gateway.envelope.recipient.runtime_source == "external"
    assert gateway.envelope.recipient.thread_id is None


@pytest.mark.asyncio
async def test_chat_delivery_hook_fails_loudly_for_managed_agent_without_activity_reader() -> None:
    class RecordingGateway:
        called = False

        async def dispatch_notification(self, _envelope):
            self.called = True

    gateway = RecordingGateway()
    app = SimpleNamespace(state=SimpleNamespace(threads_runtime_state=SimpleNamespace(agent_runtime_gateway=gateway), user_repo=_users()))
    deliver = owner_chat_inlet.make_chat_delivery_fn(
        app,
        activity_reader=None,
        thread_repo=object(),
        user_repo=app.state.user_repo,
    )

    with pytest.raises(RuntimeError, match="Managed agent runtime is unavailable for Chat delivery wake: agent-user-1"):
        await asyncio.to_thread(deliver, _chat_delivery_request())

    assert gateway.called is False
