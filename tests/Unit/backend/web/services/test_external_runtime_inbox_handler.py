from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.threads.chat_adapters.external_inbox_handler import (
    ExternalRuntimeInboxActionError,
    ExternalRuntimeInboxHandler,
    external_inbox_key,
)
from protocols.agent_runtime import (
    AgentChatContext,
    AgentChatDeliveryEnvelope,
    AgentChatRecipient,
    AgentRuntimeActor,
    AgentRuntimeMessage,
    AgentRuntimeNotificationEnvelope,
    AgentRuntimeTransport,
)


class _RecordingWakeBus:
    def __init__(self) -> None:
        self.published: list[str] = []

    def publish(self, inbox_id: str) -> None:
        self.published.append(inbox_id)


class _FailingWakeBus:
    def publish(self, _inbox_id: str) -> None:
        raise RuntimeError("wake publish failed")


def _envelope() -> AgentChatDeliveryEnvelope:
    return AgentChatDeliveryEnvelope(
        chat=AgentChatContext(chat_id="chat-1"),
        sender=AgentRuntimeActor(user_id="human-user-1", user_type="human", display_name="Human"),
        recipient=AgentChatRecipient(agent_user_id="external-user-1", runtime_source="external"),
        message=AgentRuntimeMessage(content="<system-reminder>managed runtime prompt must not leak</system-reminder>"),
    )


def _queueing_handler(wake_bus: object) -> tuple[ExternalRuntimeInboxHandler, list[tuple[str, str, str, dict]]]:
    enqueued: list[tuple[str, str, str, dict]] = []
    handler = ExternalRuntimeInboxHandler(
        wake_bus=wake_bus,
        queue_manager=SimpleNamespace(
            enqueue=lambda content, thread_id, notification_type, **meta: enqueued.append((content, thread_id, notification_type, meta))
        ),
    )
    return handler, enqueued


def _notification_envelope(
    *,
    message: AgentRuntimeMessage,
    transport: AgentRuntimeTransport | None = None,
) -> AgentRuntimeNotificationEnvelope:
    return AgentRuntimeNotificationEnvelope(
        event_type="relationship.requested",
        recipient=AgentChatRecipient(agent_user_id="external-user-1", runtime_source="external"),
        sender=AgentRuntimeActor(user_id="human-user-1", user_type="human", display_name="Human", source="relationship"),
        message=message,
        notification_type="relationship",
        transport=transport or AgentRuntimeTransport(),
    )


@pytest.mark.asyncio
async def test_external_runtime_inbox_handler_queues_chat_wake_token_only() -> None:
    wake_bus = _RecordingWakeBus()
    handler, enqueued = _queueing_handler(wake_bus)

    result = await handler.dispatch(_envelope())

    assert result.status == "accepted"
    assert result.thread_id == external_inbox_key("external-user-1")
    assert len(enqueued) == 1
    content, inbox_id, notification_type, meta = enqueued[0]
    payload = json.loads(content)
    assert inbox_id == "external:external-user-1"
    assert notification_type == "chat"
    assert meta["source"] == "external"
    assert meta["sender_id"] == "human-user-1"
    assert meta["sender_name"] == "Human"
    assert meta["wake"] is False
    assert payload == {"event_type": "chat.message", "chat_id": "chat-1"}
    assert wake_bus.published == ["external:external-user-1"]
    assert "managed runtime prompt must not leak" not in content


@pytest.mark.asyncio
async def test_external_runtime_inbox_handler_wraps_chat_wake_failure_after_enqueue() -> None:
    handler, enqueued = _queueing_handler(_FailingWakeBus())

    with pytest.raises(ExternalRuntimeInboxActionError) as exc_info:
        await handler.dispatch(_envelope())

    assert len(enqueued) == 1
    assert exc_info.value.inbox_id == "external:external-user-1"
    assert exc_info.value.notification_type == "chat"
    assert str(exc_info.value.__cause__) == "wake publish failed"


@pytest.mark.asyncio
async def test_external_runtime_inbox_handler_queues_generic_runtime_notification() -> None:
    wake_bus = _RecordingWakeBus()
    handler, enqueued = _queueing_handler(wake_bus)
    envelope = _notification_envelope(
        message=AgentRuntimeMessage(
            content="Human requested a relationship with you.",
            metadata={"relationship_id": "hire_visit:external-user-1:human-user-1"},
        ),
        transport=AgentRuntimeTransport(
            delivery_id="delivery-1",
            correlation_id="corr-1",
            idempotency_key="idem-1",
        ),
    )

    result = await handler.dispatch_notification(envelope)

    assert result.status == "accepted"
    assert result.thread_id == external_inbox_key("external-user-1")
    content, inbox_id, notification_type, meta = enqueued[0]
    payload = json.loads(content)
    assert inbox_id == "external:external-user-1"
    assert notification_type == "relationship"
    assert meta["source"] == "external"
    assert meta["sender_id"] == "human-user-1"
    assert meta["sender_name"] == "Human"
    assert meta["wake"] is False
    assert wake_bus.published == ["external:external-user-1"]
    assert payload == {
        "event_type": "relationship.requested",
        "sender_id": "human-user-1",
        "sender_name": "Human",
        "summary": "Human requested a relationship with you.",
        "relationship_id": "hire_visit:external-user-1:human-user-1",
        "delivery_id": "delivery-1",
        "correlation_id": "corr-1",
        "idempotency_key": "idem-1",
    }


@pytest.mark.asyncio
async def test_external_runtime_inbox_handler_wraps_notification_wake_failure_after_enqueue() -> None:
    handler, enqueued = _queueing_handler(_FailingWakeBus())
    envelope = _notification_envelope(
        message=AgentRuntimeMessage(content="Human requested a relationship with you."),
    )

    with pytest.raises(ExternalRuntimeInboxActionError) as exc_info:
        await handler.dispatch_notification(envelope)

    assert len(enqueued) == 1
    assert exc_info.value.inbox_id == "external:external-user-1"
    assert exc_info.value.notification_type == "relationship"
    assert str(exc_info.value.__cause__) == "wake publish failed"


def test_external_inbox_key_rejects_blank_user_id() -> None:
    with pytest.raises(RuntimeError, match="external runtime inbox requires recipient user id"):
        external_inbox_key(" ")
