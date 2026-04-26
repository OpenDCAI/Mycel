from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.threads.chat_adapters import chat_inlet as owner_chat_inlet
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
async def test_chat_delivery_hook_uses_request_sender_type() -> None:
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


def test_make_chat_delivery_fn_requires_activity_reader():
    app = SimpleNamespace(
        state=SimpleNamespace(
            threads_runtime_state=SimpleNamespace(agent_runtime_gateway=object(), activity_reader=None),
        )
    )

    with pytest.raises(RuntimeError, match="Agent runtime thread activity reader is not configured"):
        owner_chat_inlet.make_chat_delivery_fn(
            app,
            activity_reader=None,
            thread_repo=object(),
        )
