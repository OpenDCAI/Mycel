from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.threads.chat_adapters import relationship_inlet
from messaging.contracts import RelationshipRow
from protocols.agent_runtime import AgentThreadInputResult


def _relationship_row(
    *,
    user_low: str = "agent-user-1",
    user_high: str = "human-user-1",
    initiator_user_id: str = "human-user-1",
    message: str | None = None,
) -> RelationshipRow:
    now = datetime(2026, 4, 26, tzinfo=UTC)
    return RelationshipRow(
        id=f"hire_visit:{user_low}:{user_high}",
        user_low=user_low,
        user_high=user_high,
        kind="hire_visit",
        state="pending",
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


@pytest.mark.asyncio
async def test_relationship_request_notification_dispatches_thread_input_to_agent_target() -> None:
    class RecordingGateway:
        envelope = None

        async def dispatch_thread_input(self, envelope):
            self.envelope = envelope
            return AgentThreadInputResult(status="injected", routing="steer", thread_id=envelope.thread_id)

    gateway = RecordingGateway()
    user_repo = SimpleNamespace(
        get_by_id=lambda uid: {
            "human-user-1": SimpleNamespace(
                id="human-user-1",
                type="human",
                display_name="Human",
                avatar=None,
            ),
            "agent-user-1": SimpleNamespace(
                id="agent-user-1",
                type="agent",
                display_name="Toad",
                avatar=None,
            ),
        }.get(uid)
    )
    notify = relationship_inlet.make_relationship_request_notification_fn(
        _hook_app(gateway),
        activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
        thread_repo=_thread_repo(),
        user_repo=user_repo,
    )

    await asyncio.to_thread(notify, _relationship_row(message="Please add me to the planning chat."))

    assert gateway.envelope is not None
    assert gateway.envelope.thread_id == "thread-main"
    assert gateway.envelope.sender.user_id == "human-user-1"
    assert gateway.envelope.sender.user_type == "human"
    assert gateway.envelope.sender.display_name == "Human"
    assert gateway.envelope.sender.source == "relationship"
    assert "Human requested a relationship with you." in gateway.envelope.message.content
    assert "Please add me to the planning chat." in gateway.envelope.message.content
    assert gateway.envelope.message.metadata == {"relationship_id": "hire_visit:agent-user-1:human-user-1"}


@pytest.mark.asyncio
async def test_relationship_request_notification_does_not_dispatch_to_non_agent_target() -> None:
    class RecordingGateway:
        called = False

        async def dispatch_thread_input(self, _envelope):
            self.called = True

    gateway = RecordingGateway()
    user_repo = SimpleNamespace(
        get_by_id=lambda uid: {
            "human-user-1": SimpleNamespace(id="human-user-1", type="human", display_name="Human", avatar=None),
            "human-user-2": SimpleNamespace(id="human-user-2", type="human", display_name="Other", avatar=None),
        }.get(uid)
    )
    notify = relationship_inlet.make_relationship_request_notification_fn(
        _hook_app(gateway),
        activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
        thread_repo=SimpleNamespace(get_by_user_id=lambda _uid: None, list_by_agent_user=lambda _uid: []),
        user_repo=user_repo,
    )

    await asyncio.to_thread(
        notify,
        _relationship_row(user_low="human-user-1", user_high="human-user-2", initiator_user_id="human-user-1"),
    )

    assert gateway.called is False


@pytest.mark.asyncio
async def test_relationship_request_notification_fails_when_agent_target_has_no_runtime_thread() -> None:
    class RecordingGateway:
        called = False

        async def dispatch_thread_input(self, _envelope):
            self.called = True

    gateway = RecordingGateway()
    user_repo = SimpleNamespace(
        get_by_id=lambda uid: {
            "human-user-1": SimpleNamespace(id="human-user-1", type="human", display_name="Human", avatar=None),
            "agent-user-1": SimpleNamespace(id="agent-user-1", type="agent", display_name="Toad", avatar=None),
        }.get(uid)
    )
    notify = relationship_inlet.make_relationship_request_notification_fn(
        _hook_app(gateway),
        activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
        thread_repo=SimpleNamespace(get_by_user_id=lambda _uid: None, list_by_agent_user=lambda _uid: []),
        user_repo=user_repo,
    )

    with pytest.raises(RuntimeError, match="Relationship request target agent has no runtime thread: agent-user-1"):
        await asyncio.to_thread(notify, _relationship_row())

    assert gateway.called is False
