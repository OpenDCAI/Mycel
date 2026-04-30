from __future__ import annotations

import json
from typing import Any

from protocols import agent_runtime as agent_runtime_protocol


def external_inbox_key(user_id: str) -> str:
    normalized = str(user_id or "").strip()
    if not normalized:
        raise RuntimeError("external runtime inbox requires recipient user id")
    return f"external:{normalized}"


class ExternalRuntimeInboxHandler:
    def __init__(self, *, queue_manager: Any, wake_bus: Any | None = None) -> None:
        self._queue_manager = queue_manager
        self._wake_bus = wake_bus

    async def dispatch(self, envelope: agent_runtime_protocol.AgentChatDeliveryEnvelope) -> agent_runtime_protocol.AgentChatDeliveryResult:
        inbox_id = external_inbox_key(envelope.recipient.agent_user_id)
        self._queue_manager.enqueue(
            json.dumps(
                {"event_type": "chat.message", "chat_id": envelope.chat.chat_id},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            inbox_id,
            "chat",
            source="external",
            sender_id=envelope.sender.user_id,
            sender_name=envelope.sender.display_name,
            wake=self._wake_bus is None and envelope.wake,
        )
        if self._wake_bus is not None and envelope.wake:
            self._wake_bus.publish(inbox_id)
        return agent_runtime_protocol.AgentChatDeliveryResult(status="accepted", thread_id=inbox_id)

    async def dispatch_notification(
        self, envelope: agent_runtime_protocol.AgentRuntimeNotificationEnvelope
    ) -> agent_runtime_protocol.AgentRuntimeNotificationResult:
        inbox_id = external_inbox_key(envelope.recipient.agent_user_id)
        payload = {
            "event_type": envelope.event_type,
            "sender_id": envelope.sender.user_id,
            "sender_name": envelope.sender.display_name,
            "summary": envelope.message.content,
        }
        if envelope.message.metadata:
            payload.update(envelope.message.metadata)
        self._queue_manager.enqueue(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            inbox_id,
            envelope.notification_type,
            source="external",
            sender_id=envelope.sender.user_id,
            sender_name=envelope.sender.display_name,
            wake=self._wake_bus is None and envelope.wake,
        )
        if self._wake_bus is not None and envelope.wake:
            self._wake_bus.publish(inbox_id)
        return agent_runtime_protocol.AgentRuntimeNotificationResult(status="accepted", thread_id=inbox_id)
