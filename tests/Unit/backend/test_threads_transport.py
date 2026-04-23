from __future__ import annotations

import pytest

from backend.threads import transport as threads_transport
from protocols.agent_runtime import AgentRuntimeActor, AgentRuntimeMessage, AgentThreadInputEnvelope


def _envelope() -> AgentThreadInputEnvelope:
    return AgentThreadInputEnvelope(
        thread_id="thread-1",
        sender=AgentRuntimeActor(user_id="owner-1", user_type="human", display_name="Owner"),
        message=AgentRuntimeMessage(content="hello"),
        enable_trajectory=True,
    )


@pytest.mark.asyncio
async def test_http_thread_input_transport_posts_protocol_payload_without_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            captured["raised"] = True

        def json(self) -> dict[str, str]:
            return {
                "status": "started",
                "routing": "direct",
                "thread_id": "thread-1",
                "run_id": "run-1",
            }

    class _Client:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            return None

        async def post(self, url: str, *, json: dict) -> _Response:
            captured["url"] = url
            captured["json"] = json
            return _Response()

    monkeypatch.setattr(threads_transport.httpx, "AsyncClient", _Client)

    transport = threads_transport.HttpThreadInputTransport(base_url="http://threads-backend")
    result = await transport.dispatch_thread_input(_envelope())

    assert captured["timeout"] == 10.0
    assert captured["trust_env"] is False
    assert captured["url"] == "http://threads-backend/api/internal/agent-runtime/thread-input"
    assert captured["json"] == {
        "thread_id": "thread-1",
        "sender": {
            "user_id": "owner-1",
            "user_type": "human",
            "display_name": "Owner",
            "avatar_url": None,
            "source": None,
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
        "enable_trajectory": True,
        "protocol_version": "agent.thread.input.v1",
        "event_type": "thread.input",
    }
    assert captured["raised"] is True
    assert result.status == "started"
    assert result.routing == "direct"
    assert result.thread_id == "thread-1"
    assert result.run_id == "run-1"
