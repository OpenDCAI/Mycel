from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.threads.chat_adapters.bootstrap import build_agent_runtime_gateway
from protocols.agent_runtime import (
    AgentChatContext,
    AgentChatDeliveryEnvelope,
    AgentChatRecipient,
    AgentRuntimeActor,
    AgentRuntimeMessage,
)


@pytest.mark.asyncio
async def test_gateway_chat_delivery_uses_preselected_thread_id_from_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[tuple[str, str, str]] = []
    enqueued: list[tuple[str, str]] = []

    async def _fake_get_or_create_agent(_app, _sandbox_type: str, *, thread_id: str):
        return SimpleNamespace(id=f"agent-for-{thread_id}")

    monkeypatch.setattr("backend.threads.chat_adapters.bootstrap.get_or_create_agent", _fake_get_or_create_agent)
    monkeypatch.setattr("backend.threads.chat_adapters.bootstrap.resolve_thread_sandbox", lambda _app, _thread_id: "local")
    monkeypatch.setattr("backend.threads.chat_adapters.bootstrap._ensure_thread_handlers", lambda *_args, **_kwargs: None)

    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(
                get_by_id=lambda thread_id: {"id": thread_id, "sandbox_type": "local"},
                get_by_user_id=lambda _uid: (_ for _ in ()).throw(AssertionError("handler should not resolve thread id locally")),
                list_by_agent_user=lambda _uid: (_ for _ in ()).throw(
                    AssertionError("handler should not scan runtime thread candidates locally")
                ),
            ),
            agent_pool={},
            queue_manager=SimpleNamespace(
                enqueue=lambda content, thread_id, _notification_type, **_meta: enqueued.append((content, thread_id))
            ),
            thread_cwd={},
            thread_sandbox={},
            thread_tasks={},
            thread_locks={},
            thread_locks_guard=asyncio.Lock(),
        )
    )
    typing_tracker = SimpleNamespace(start_chat=lambda thread_id, chat_id, user_id: started.append((thread_id, chat_id, user_id)))

    envelope = AgentChatDeliveryEnvelope(
        chat=AgentChatContext(chat_id="chat-1"),
        sender=AgentRuntimeActor(user_id="human-user-1", user_type="human", display_name="Human"),
        recipient=AgentChatRecipient(agent_user_id="agent-user-1", runtime_source="mycel", thread_id="thread-preselected"),
        message=AgentRuntimeMessage(content="hello", signal="ping"),
    )

    result = await build_agent_runtime_gateway(app, typing_tracker=typing_tracker).dispatch_chat(envelope)

    assert result.status == "accepted"
    assert result.thread_id == "thread-preselected"
    assert started == [("thread-preselected", "chat-1", "agent-user-1")]
    assert enqueued == [("hello", "thread-preselected")]
