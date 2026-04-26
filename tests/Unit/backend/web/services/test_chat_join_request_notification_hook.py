from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.threads.chat_adapters import chat_join_inlet
from protocols.agent_runtime import AgentThreadInputResult


def _hook_app(gateway: object) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(threads_runtime_state=SimpleNamespace(agent_runtime_gateway=gateway)))


def _thread_repo() -> SimpleNamespace:
    default_thread = {"id": "thread-main", "agent_user_id": "agent-user-1", "is_main": True, "branch_index": 0}
    return SimpleNamespace(
        get_by_user_id=lambda uid: default_thread if uid == "agent-user-1" else None,
        list_by_agent_user=lambda uid: [default_thread] if uid == "agent-user-1" else [],
    )


@pytest.mark.asyncio
async def test_chat_join_rejection_notification_dispatches_to_agent_requester() -> None:
    class RecordingGateway:
        envelope = None

        async def dispatch_thread_input(self, envelope):
            self.envelope = envelope
            return AgentThreadInputResult(status="injected", routing="steer", thread_id=envelope.thread_id)

    gateway = RecordingGateway()
    user_repo = SimpleNamespace(
        get_by_id=lambda uid: {
            "owner-1": SimpleNamespace(id="owner-1", type="human", display_name="Owner", avatar=None),
            "agent-user-1": SimpleNamespace(id="agent-user-1", type="agent", display_name="Toad", avatar=None),
        }.get(uid)
    )
    notify = chat_join_inlet.make_chat_join_rejection_notification_fn(
        _hook_app(gateway),
        activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
        thread_repo=_thread_repo(),
        user_repo=user_repo,
    )

    await asyncio.to_thread(
        notify,
        {
            "id": "chat_join:chat-1:agent-user-1",
            "chat_id": "chat-1",
            "requester_user_id": "agent-user-1",
            "state": "rejected",
            "decided_by_user_id": "owner-1",
        },
    )

    assert gateway.envelope is not None
    assert gateway.envelope.thread_id == "thread-main"
    assert gateway.envelope.sender.user_id == "owner-1"
    assert gateway.envelope.sender.user_type == "human"
    assert gateway.envelope.sender.display_name == "Owner"
    assert gateway.envelope.sender.source == "chat_join"
    assert "Owner rejected your request to join chat chat-1." in gateway.envelope.message.content
    assert gateway.envelope.message.metadata == {
        "chat_join_request_id": "chat_join:chat-1:agent-user-1",
        "chat_id": "chat-1",
        "state": "rejected",
    }


@pytest.mark.asyncio
async def test_chat_join_rejection_notification_ignores_non_agent_requester() -> None:
    class RecordingGateway:
        called = False

        async def dispatch_thread_input(self, _envelope):
            self.called = True

    gateway = RecordingGateway()
    user_repo = SimpleNamespace(
        get_by_id=lambda uid: {
            "owner-1": SimpleNamespace(id="owner-1", type="human", display_name="Owner", avatar=None),
            "human-1": SimpleNamespace(id="human-1", type="human", display_name="Human", avatar=None),
        }.get(uid)
    )
    notify = chat_join_inlet.make_chat_join_rejection_notification_fn(
        _hook_app(gateway),
        activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
        thread_repo=SimpleNamespace(get_by_user_id=lambda _uid: None, list_by_agent_user=lambda _uid: []),
        user_repo=user_repo,
    )

    await asyncio.to_thread(
        notify,
        {
            "id": "chat_join:chat-1:human-1",
            "chat_id": "chat-1",
            "requester_user_id": "human-1",
            "state": "rejected",
            "decided_by_user_id": "owner-1",
        },
    )

    assert gateway.called is False
