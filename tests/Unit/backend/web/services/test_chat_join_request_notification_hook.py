from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.threads.chat_adapters import chat_join_inlet


def _hook_app(gateway: object) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(threads_runtime_state=SimpleNamespace(agent_runtime_gateway=gateway)))


def _thread_repo() -> SimpleNamespace:
    default_thread = {"id": "thread-main", "agent_user_id": "agent-user-1", "is_main": True, "branch_index": 0}
    return SimpleNamespace(
        get_by_user_id=lambda uid: default_thread if uid == "agent-user-1" else None,
        list_by_agent_user=lambda uid: [default_thread] if uid == "agent-user-1" else [],
    )


def _empty_thread_repo() -> SimpleNamespace:
    return SimpleNamespace(get_by_user_id=lambda _uid: None, list_by_agent_user=lambda _uid: [])


def _activity_reader() -> SimpleNamespace:
    return SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: [])


def _user(user_id: str, user_type: str, display_name: str) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, type=user_type, display_name=display_name, avatar=None)


def _user_repo(*users: SimpleNamespace) -> SimpleNamespace:
    rows = {user.id: user for user in users}
    return SimpleNamespace(get_by_id=lambda uid: rows.get(uid))


class _RecordingGateway:
    def __init__(self) -> None:
        self.envelopes = []

    async def dispatch_notification(self, envelope):
        self.envelopes.append(envelope)
        thread_id = envelope.recipient.thread_id or f"external:{envelope.recipient.agent_user_id}"
        return SimpleNamespace(status="accepted", thread_id=thread_id)


def _only_envelope(gateway: _RecordingGateway):
    assert len(gateway.envelopes) == 1
    return gateway.envelopes[0]


def test_chat_join_rejection_notification_planner_returns_runtime_action() -> None:
    user_repo = _user_repo(_user("owner-1", "human", "Owner"))
    planner = chat_join_inlet.chat_join_rejection_notification_action_planner(user_repo)

    actions = planner(
        {
            "id": "chat_join:chat-1:agent-user-1",
            "chat_id": "chat-1",
            "requester_user_id": "agent-user-1",
            "state": "rejected",
            "decided_by_user_id": "owner-1",
        }
    )

    assert len(actions) == 1
    action = actions[0]
    assert action.context == "Chat join rejection"
    assert action.recipient_user_id == "agent-user-1"
    assert action.sender_user_id == "owner-1"
    assert action.sender_source == "chat_join"
    assert action.event_type == "chat.join.rejected"
    assert action.notification_type == "chat_join"
    assert action.content == "Owner rejected your request to join chat chat-1."
    assert action.metadata == {
        "chat_join_request_id": "chat_join:chat-1:agent-user-1",
        "chat_id": "chat-1",
        "state": "rejected",
    }
    assert action.include_sender_avatar is True


@pytest.mark.asyncio
async def test_chat_join_rejection_notification_dispatches_runtime_notification_to_agent_requester() -> None:
    gateway = _RecordingGateway()
    user_repo = _user_repo(_user("owner-1", "human", "Owner"), _user("agent-user-1", "agent", "Agent"))
    notify = chat_join_inlet.make_chat_join_rejection_notification_fn(
        _hook_app(gateway),
        activity_reader=_activity_reader(),
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

    envelope = _only_envelope(gateway)
    assert envelope.recipient.agent_user_id == "agent-user-1"
    assert envelope.recipient.runtime_source == "mycel"
    assert envelope.recipient.thread_id == "thread-main"
    assert envelope.sender.user_id == "owner-1"
    assert envelope.sender.user_type == "human"
    assert envelope.sender.display_name == "Owner"
    assert envelope.sender.source == "chat_join"
    assert envelope.event_type == "chat.join.rejected"
    assert envelope.notification_type == "chat_join"
    assert "Owner rejected your request to join chat chat-1." in envelope.message.content
    assert envelope.message.metadata == {
        "chat_join_request_id": "chat_join:chat-1:agent-user-1",
        "chat_id": "chat-1",
        "state": "rejected",
    }


@pytest.mark.asyncio
async def test_chat_join_rejection_notification_dispatches_runtime_notification_to_external_requester() -> None:
    gateway = _RecordingGateway()
    user_repo = _user_repo(_user("owner-1", "human", "Owner"), _user("external-user-1", "external", "External"))
    notify = chat_join_inlet.make_chat_join_rejection_notification_fn(
        _hook_app(gateway),
        activity_reader=None,
        thread_repo=_empty_thread_repo(),
        user_repo=user_repo,
    )

    await asyncio.to_thread(
        notify,
        {
            "id": "chat_join:chat-1:external-user-1",
            "chat_id": "chat-1",
            "requester_user_id": "external-user-1",
            "state": "rejected",
            "decided_by_user_id": "owner-1",
        },
    )

    envelope = _only_envelope(gateway)
    assert envelope.recipient.agent_user_id == "external-user-1"
    assert envelope.recipient.runtime_source == "external"
    assert envelope.sender.user_id == "owner-1"
    assert envelope.sender.user_type == "human"
    assert envelope.sender.display_name == "Owner"
    assert envelope.sender.source == "chat_join"
    assert envelope.event_type == "chat.join.rejected"
    assert envelope.notification_type == "chat_join"
    assert "Owner rejected your request to join chat chat-1." in envelope.message.content
    assert envelope.message.metadata == {
        "chat_join_request_id": "chat_join:chat-1:external-user-1",
        "chat_id": "chat-1",
        "state": "rejected",
    }


@pytest.mark.asyncio
async def test_chat_join_rejection_notification_skips_agent_wake_when_no_runtime_thread() -> None:
    gateway = _RecordingGateway()
    user_repo = _user_repo(_user("owner-1", "human", "Owner"), _user("agent-user-1", "agent", "Agent"))
    notify = chat_join_inlet.make_chat_join_rejection_notification_fn(
        _hook_app(gateway),
        activity_reader=_activity_reader(),
        thread_repo=_empty_thread_repo(),
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

    assert gateway.envelopes == []


@pytest.mark.asyncio
async def test_chat_join_rejection_notification_ignores_human_requester() -> None:
    gateway = _RecordingGateway()
    user_repo = _user_repo(_user("owner-1", "human", "Owner"), _user("human-1", "human", "Human"))
    notify = chat_join_inlet.make_chat_join_rejection_notification_fn(
        _hook_app(gateway),
        activity_reader=_activity_reader(),
        thread_repo=_empty_thread_repo(),
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

    assert gateway.envelopes == []
