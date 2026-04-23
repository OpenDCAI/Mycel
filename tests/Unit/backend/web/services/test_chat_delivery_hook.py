from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.chat import runtime_delivery as owner_chat_delivery
from messaging.delivery.dispatcher import ChatDeliveryRequest


def _hook_app(gateway: object) -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(
            threads_runtime_state=SimpleNamespace(
                chat_transport=gateway,
            ),
        )
    )


@pytest.mark.asyncio
async def test_chat_delivery_hook_propagates_runtime_gateway_failures() -> None:
    class FailingTransport:
        def deliver_chat(self, _envelope):
            raise RuntimeError("runtime gateway down")

    app = _hook_app(FailingTransport())
    deliver = owner_chat_delivery.make_chat_delivery_fn(transport=app.state.threads_runtime_state.chat_transport)
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
    class RecordingTransport:
        envelope = None

        def deliver_chat(self, envelope):
            self.envelope = envelope

    transport = RecordingTransport()
    app = _hook_app(transport)
    deliver = owner_chat_delivery.make_chat_delivery_fn(transport=app.state.threads_runtime_state.chat_transport)
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

    assert transport.envelope is not None
    assert transport.envelope.sender.user_type == "human"
    assert "New message from Human in chat chat-1 (3 unread)." in transport.envelope.message.content
    assert 'read_messages(chat_id="chat-1")' in transport.envelope.message.content
    assert transport.envelope.extensions["mycel"]["raw_content"] == "hello"


@pytest.mark.asyncio
async def test_chat_delivery_hook_requires_recipient_user_type() -> None:
    class RecordingTransport:
        called = False

        def deliver_chat(self, _envelope):
            self.called = True

    transport = RecordingTransport()
    app = _hook_app(transport)
    deliver = owner_chat_delivery.make_chat_delivery_fn(transport=app.state.threads_runtime_state.chat_transport)
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

    assert transport.called is False


@pytest.mark.asyncio
async def test_chat_delivery_hook_requires_recipient_user_id() -> None:
    class RecordingTransport:
        called = False

        def deliver_chat(self, _envelope):
            self.called = True

    transport = RecordingTransport()
    app = _hook_app(transport)
    deliver = owner_chat_delivery.make_chat_delivery_fn(transport=app.state.threads_runtime_state.chat_transport)
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

    assert transport.called is False


def test_make_chat_delivery_fn_requires_transport():
    with pytest.raises(RuntimeError, match="Chat runtime transport is not configured"):
        owner_chat_delivery.make_chat_delivery_fn(transport=None)
