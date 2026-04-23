from __future__ import annotations

import asyncio

import pytest

from backend.chat import transport as chat_transport
from protocols.agent_runtime import (
    AgentChatContext,
    AgentChatDeliveryEnvelope,
    AgentChatRecipient,
    AgentRuntimeActor,
    AgentRuntimeMessage,
)


def _envelope():
    return AgentChatDeliveryEnvelope(
        chat=AgentChatContext(chat_id="chat-1"),
        sender=AgentRuntimeActor(user_id="human-1", user_type="human", display_name="Human"),
        recipient=AgentChatRecipient(agent_user_id="agent-1", runtime_source="mycel"),
        message=AgentRuntimeMessage(content="hello"),
    )


@pytest.mark.asyncio
async def test_inprocess_chat_transport_bridges_to_runtime_gateway() -> None:
    seen = []

    class _Gateway:
        async def dispatch_chat(self, envelope):
            seen.append(envelope)

    transport = chat_transport.InProcessChatRuntimeTransport(runtime_gateway=_Gateway(), loop=asyncio.get_running_loop())

    await asyncio.to_thread(transport.deliver_chat, _envelope())

    assert len(seen) == 1


def test_inprocess_chat_transport_requires_runtime_gateway() -> None:
    with pytest.raises(RuntimeError, match="Agent runtime gateway is not configured"):
        chat_transport.InProcessChatRuntimeTransport(runtime_gateway=None, loop=object())


def test_http_chat_transport_posts_protocol_payload_without_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            captured["raised"] = True

    class _Client:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def post(self, url: str, *, json: dict) -> _Response:
            captured["url"] = url
            captured["json"] = json
            return _Response()

    monkeypatch.setattr(chat_transport.httpx, "Client", _Client)

    transport = chat_transport.HttpChatRuntimeTransport(base_url="http://threads-backend")
    transport.deliver_chat(_envelope())

    assert captured["timeout"] == 10.0
    assert captured["trust_env"] is False
    assert captured["url"] == "http://threads-backend/api/internal/agent-runtime/chat-deliveries"
    assert captured["json"] == {
        "chat": {"chat_id": "chat-1", "title": None},
        "sender": {
            "user_id": "human-1",
            "user_type": "human",
            "display_name": "Human",
            "avatar_url": None,
            "source": None,
        },
        "recipient": {
            "agent_user_id": "agent-1",
            "runtime_source": "mycel",
        },
        "message": {
            "content": "hello",
            "content_type": "text",
            "message_id": None,
            "signal": None,
            "created_at": None,
            "attachments": None,
            "metadata": None,
        },
        "transport": {
            "delivery_id": None,
            "correlation_id": None,
            "idempotency_key": None,
        },
        "protocol_version": "agent.chat.delivery.v1",
        "event_type": "chat.message",
        "extensions": None,
    }
    assert captured["raised"] is True
