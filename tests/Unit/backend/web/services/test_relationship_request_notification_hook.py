from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.threads.chat_adapters import relationship_inlet
from messaging.contracts import RelationshipRow, RelationshipState


def _relationship_row(
    *,
    user_low: str = "agent-user-1",
    user_high: str = "human-user-1",
    initiator_user_id: str = "human-user-1",
    message: str | None = None,
    state: RelationshipState = "pending",
) -> RelationshipRow:
    now = datetime(2026, 4, 26, tzinfo=UTC)
    return RelationshipRow(
        id=f"hire_visit:{user_low}:{user_high}",
        user_low=user_low,
        user_high=user_high,
        kind="hire_visit",
        state=state,
        initiator_user_id=initiator_user_id,
        message=message,
        created_at=now,
        updated_at=now,
    )


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


def test_relationship_request_notification_action_carries_runtime_contract() -> None:
    user_repo = _user_repo(_user("human-user-1", "human", "Human"))

    action = relationship_inlet.relationship_request_notification_action(
        _relationship_row(message="Please add me."),
        user_repo=user_repo,
    )

    assert action.context == "Relationship request"
    assert action.recipient_user_id == "agent-user-1"
    assert action.sender_user_id == "human-user-1"
    assert action.sender_source == "relationship"
    assert action.event_type == "relationship.requested"
    assert action.notification_type == "relationship"
    assert action.content == (
        "Human requested a relationship with you. Message: Please add me. "
        "Review the pending relationship request in Mycel, then approve or reject it."
    )
    assert action.metadata == {"relationship_id": "hire_visit:agent-user-1:human-user-1"}
    assert action.include_sender_avatar is True


def test_relationship_decision_notification_action_carries_runtime_contract() -> None:
    user_repo = _user_repo(_user("human-user-1", "human", "Human"))

    action = relationship_inlet.relationship_decision_notification_action(
        relationship_inlet.RelationshipDecisionChange(
            row=_relationship_row(initiator_user_id="agent-user-1", state="visit"),
            event="approve",
        ),
        user_repo=user_repo,
    )

    assert action.context == "Relationship request"
    assert action.recipient_user_id == "agent-user-1"
    assert action.sender_user_id == "human-user-1"
    assert action.sender_source == "relationship"
    assert action.event_type == "relationship.approved"
    assert action.notification_type == "relationship"
    assert action.content == "Human approved your relationship request."
    assert action.metadata == {
        "relationship_id": "hire_visit:agent-user-1:human-user-1",
        "event": "approve",
        "state": "visit",
    }
    assert action.include_sender_avatar is True


@pytest.mark.asyncio
async def test_relationship_request_notification_dispatches_runtime_notification_to_agent_target() -> None:
    gateway = _RecordingGateway()
    user_repo = _user_repo(_user("human-user-1", "human", "Human"), _user("agent-user-1", "agent", "Agent"))
    notify = relationship_inlet.make_relationship_request_notification_fn(
        _hook_app(gateway),
        activity_reader=_activity_reader(),
        thread_repo=_thread_repo(),
        user_repo=user_repo,
    )

    await asyncio.to_thread(notify, _relationship_row(message="Please add me to the planning chat."))

    envelope = _only_envelope(gateway)
    assert envelope.recipient.agent_user_id == "agent-user-1"
    assert envelope.recipient.runtime_source == "mycel"
    assert envelope.recipient.thread_id == "thread-main"
    assert envelope.sender.user_id == "human-user-1"
    assert envelope.sender.user_type == "human"
    assert envelope.sender.display_name == "Human"
    assert envelope.sender.source == "relationship"
    assert envelope.event_type == "relationship.requested"
    assert envelope.notification_type == "relationship"
    assert "Human requested a relationship with you." in envelope.message.content
    assert "Please add me to the planning chat." in envelope.message.content
    assert envelope.message.metadata == {"relationship_id": "hire_visit:agent-user-1:human-user-1"}


@pytest.mark.asyncio
async def test_relationship_request_notification_dispatches_external_runtime_notification_to_external_target() -> None:
    gateway = _RecordingGateway()
    user_repo = _user_repo(_user("human-user-1", "human", "Human"), _user("external-user-1", "external", "External"))
    notify = relationship_inlet.make_relationship_request_notification_fn(
        _hook_app(gateway),
        activity_reader=None,
        thread_repo=_empty_thread_repo(),
        user_repo=user_repo,
    )

    await asyncio.to_thread(
        notify,
        _relationship_row(
            user_low="external-user-1",
            user_high="human-user-1",
            initiator_user_id="human-user-1",
            message="Please add me.",
        ),
    )

    envelope = _only_envelope(gateway)
    assert envelope.recipient.agent_user_id == "external-user-1"
    assert envelope.recipient.runtime_source == "external"
    assert envelope.sender.user_id == "human-user-1"
    assert envelope.sender.source == "relationship"
    assert envelope.event_type == "relationship.requested"
    assert "Human requested a relationship with you." in envelope.message.content
    assert envelope.message.metadata == {"relationship_id": "hire_visit:external-user-1:human-user-1"}


@pytest.mark.asyncio
async def test_relationship_request_notification_does_not_dispatch_to_non_agent_target() -> None:
    gateway = _RecordingGateway()
    user_repo = _user_repo(_user("human-user-1", "human", "Human"), _user("human-user-2", "human", "Other"))
    notify = relationship_inlet.make_relationship_request_notification_fn(
        _hook_app(gateway),
        activity_reader=_activity_reader(),
        thread_repo=_empty_thread_repo(),
        user_repo=user_repo,
    )

    await asyncio.to_thread(
        notify,
        _relationship_row(user_low="human-user-1", user_high="human-user-2", initiator_user_id="human-user-1"),
    )

    assert gateway.envelopes == []


@pytest.mark.asyncio
async def test_relationship_request_notification_skips_agent_wake_when_no_runtime_thread() -> None:
    gateway = _RecordingGateway()
    user_repo = _user_repo(_user("human-user-1", "human", "Human"), _user("agent-user-1", "agent", "Agent"))
    notify = relationship_inlet.make_relationship_request_notification_fn(
        _hook_app(gateway),
        activity_reader=_activity_reader(),
        thread_repo=_empty_thread_repo(),
        user_repo=user_repo,
    )

    await asyncio.to_thread(notify, _relationship_row())

    assert gateway.envelopes == []


@pytest.mark.asyncio
async def test_relationship_decision_notification_dispatches_runtime_notification_to_agent_requester() -> None:
    gateway = _RecordingGateway()
    user_repo = _user_repo(_user("human-user-1", "human", "Human"), _user("agent-user-1", "agent", "Agent"))
    notify = relationship_inlet.make_relationship_decision_notification_fn(
        _hook_app(gateway),
        activity_reader=_activity_reader(),
        thread_repo=_thread_repo(),
        user_repo=user_repo,
    )

    await asyncio.to_thread(
        notify,
        _relationship_row(
            user_low="agent-user-1",
            user_high="human-user-1",
            initiator_user_id="agent-user-1",
            state="visit",
        ),
        "approve",
    )

    envelope = _only_envelope(gateway)
    assert envelope.recipient.agent_user_id == "agent-user-1"
    assert envelope.recipient.runtime_source == "mycel"
    assert envelope.recipient.thread_id == "thread-main"
    assert envelope.sender.user_id == "human-user-1"
    assert envelope.sender.user_type == "human"
    assert envelope.sender.display_name == "Human"
    assert envelope.sender.source == "relationship"
    assert envelope.event_type == "relationship.approved"
    assert envelope.notification_type == "relationship"
    assert "Human approved your relationship request." in envelope.message.content
    assert envelope.message.metadata == {
        "relationship_id": "hire_visit:agent-user-1:human-user-1",
        "event": "approve",
        "state": "visit",
    }


@pytest.mark.asyncio
async def test_relationship_decision_notification_dispatches_external_runtime_notification_to_external_requester() -> None:
    gateway = _RecordingGateway()
    user_repo = _user_repo(_user("human-user-1", "human", "Human"), _user("external-user-1", "external", "External"))
    notify = relationship_inlet.make_relationship_decision_notification_fn(
        _hook_app(gateway),
        activity_reader=None,
        thread_repo=_empty_thread_repo(),
        user_repo=user_repo,
    )

    await asyncio.to_thread(
        notify,
        _relationship_row(
            user_low="external-user-1",
            user_high="human-user-1",
            initiator_user_id="external-user-1",
            state="visit",
        ),
        "approve",
    )

    envelope = _only_envelope(gateway)
    assert envelope.recipient.agent_user_id == "external-user-1"
    assert envelope.recipient.runtime_source == "external"
    assert envelope.sender.user_id == "human-user-1"
    assert envelope.sender.source == "relationship"
    assert envelope.event_type == "relationship.approved"
    assert "Human approved your relationship request." in envelope.message.content
    assert envelope.message.metadata == {
        "relationship_id": "hire_visit:external-user-1:human-user-1",
        "event": "approve",
        "state": "visit",
    }


@pytest.mark.asyncio
async def test_relationship_decision_notification_ignores_non_agent_requester() -> None:
    gateway = _RecordingGateway()
    user_repo = _user_repo(_user("human-user-1", "human", "Human"), _user("human-user-2", "human", "Other"))
    notify = relationship_inlet.make_relationship_decision_notification_fn(
        _hook_app(gateway),
        activity_reader=_activity_reader(),
        thread_repo=_empty_thread_repo(),
        user_repo=user_repo,
    )

    await asyncio.to_thread(
        notify,
        _relationship_row(user_low="human-user-1", user_high="human-user-2", initiator_user_id="human-user-1"),
        "reject",
    )

    assert gateway.envelopes == []


@pytest.mark.asyncio
async def test_relationship_decision_notification_skips_agent_wake_when_no_runtime_thread() -> None:
    gateway = _RecordingGateway()
    user_repo = _user_repo(_user("human-user-1", "human", "Human"), _user("agent-user-1", "agent", "Agent"))
    notify = relationship_inlet.make_relationship_decision_notification_fn(
        _hook_app(gateway),
        activity_reader=_activity_reader(),
        thread_repo=_empty_thread_repo(),
        user_repo=user_repo,
    )

    await asyncio.to_thread(
        notify,
        _relationship_row(
            user_low="agent-user-1",
            user_high="human-user-1",
            initiator_user_id="agent-user-1",
            state="visit",
        ),
        "approve",
    )

    assert gateway.envelopes == []
