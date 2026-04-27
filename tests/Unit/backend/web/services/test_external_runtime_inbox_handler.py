from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.threads.chat_adapters.external_inbox_handler import ExternalRuntimeInboxHandler, external_inbox_key
from protocols.agent_runtime import (
    AgentChatContext,
    AgentChatDeliveryEnvelope,
    AgentChatRecipient,
    AgentRuntimeActor,
    AgentRuntimeMessage,
    AgentRuntimeNotificationEnvelope,
)


def _envelope() -> AgentChatDeliveryEnvelope:
    return AgentChatDeliveryEnvelope(
        chat=AgentChatContext(chat_id="chat-1"),
        sender=AgentRuntimeActor(user_id="human-user-1", user_type="human", display_name="Human"),
        recipient=AgentChatRecipient(agent_user_id="external-user-1", runtime_source="external"),
        message=AgentRuntimeMessage(content="<system-reminder>managed runtime prompt must not leak</system-reminder>"),
    )


@pytest.mark.asyncio
async def test_external_runtime_inbox_handler_queues_metadata_only_notification() -> None:
    enqueued: list[tuple[str, str, str, dict]] = []
    handler = ExternalRuntimeInboxHandler(
        queue_manager=SimpleNamespace(
            enqueue=lambda content, thread_id, notification_type, **meta: enqueued.append((content, thread_id, notification_type, meta))
        )
    )

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
    assert payload == {
        "event_type": "chat.message",
        "chat_id": "chat-1",
        "sender_id": "human-user-1",
        "sender_name": "Human",
        "summary": "New chat message from Human.",
    }


@pytest.mark.asyncio
async def test_external_runtime_inbox_handler_queues_generic_runtime_notification() -> None:
    enqueued: list[tuple[str, str, str, dict]] = []
    handler = ExternalRuntimeInboxHandler(
        queue_manager=SimpleNamespace(
            enqueue=lambda content, thread_id, notification_type, **meta: enqueued.append((content, thread_id, notification_type, meta))
        )
    )
    envelope = AgentRuntimeNotificationEnvelope(
        event_type="relationship.requested",
        recipient=AgentChatRecipient(agent_user_id="external-user-1", runtime_source="external"),
        sender=AgentRuntimeActor(user_id="human-user-1", user_type="human", display_name="Human", source="relationship"),
        message=AgentRuntimeMessage(
            content="Human requested a relationship with you.",
            metadata={"relationship_id": "hire_visit:external-user-1:human-user-1"},
        ),
        notification_type="relationship",
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
    assert payload == {
        "event_type": "relationship.requested",
        "sender_id": "human-user-1",
        "sender_name": "Human",
        "summary": "Human requested a relationship with you.",
        "relationship_id": "hire_visit:external-user-1:human-user-1",
    }


def test_external_inbox_key_rejects_blank_user_id() -> None:
    with pytest.raises(RuntimeError, match="external runtime inbox requires recipient user id"):
        external_inbox_key(" ")
