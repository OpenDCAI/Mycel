from __future__ import annotations

import json
from typing import Any

from protocols import agent_runtime as agent_runtime_protocol


def external_inbox_key(user_id: str) -> str:
    normalized = str(user_id or "").strip()
    if not normalized:
        raise RuntimeError("external runtime inbox requires recipient user id")
    return f"external:{normalized}"


class ExternalRuntimeInboxActionError(RuntimeError):
    def __init__(self, *, inbox_id: str, notification_type: str) -> None:
        super().__init__(f"External runtime inbox wake failed after enqueue: {inbox_id}")
        self.inbox_id = inbox_id
        self.notification_type = notification_type


class ExternalRuntimeInboxHandler:
    def __init__(self, *, queue_manager: Any, wake_bus: Any | None = None) -> None:
        self._queue_manager = queue_manager
        self._wake_bus = wake_bus

    def _enqueue_external_inbox_action(
        self,
        *,
        inbox_id: str,
        content: str,
        notification_type: str,
        sender_id: str,
        sender_name: str,
        wake: bool,
    ) -> None:
        self._queue_manager.enqueue(
            content,
            inbox_id,
            notification_type,
            source="external",
            sender_id=sender_id,
            sender_name=sender_name,
            wake=self._wake_bus is None and wake,
        )
        if self._wake_bus is not None and wake:
            try:
                self._wake_bus.publish(inbox_id)
            except Exception as exc:
                raise ExternalRuntimeInboxActionError(inbox_id=inbox_id, notification_type=notification_type) from exc

    async def dispatch_notification(
        self, envelope: agent_runtime_protocol.AgentRuntimeNotificationEnvelope
    ) -> agent_runtime_protocol.AgentRuntimeNotificationResult:
        inbox_id = external_inbox_key(envelope.recipient.agent_user_id)
        payload = _notification_payload(envelope)
        payload.update(_transport_payload(envelope.transport))
        self._enqueue_external_inbox_action(
            inbox_id=inbox_id,
            content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            notification_type=envelope.notification_type,
            sender_id=envelope.sender.user_id,
            sender_name=envelope.sender.display_name,
            wake=envelope.wake,
        )
        return agent_runtime_protocol.AgentRuntimeNotificationResult(status="accepted", thread_id=inbox_id)


def _notification_payload(envelope: agent_runtime_protocol.AgentRuntimeNotificationEnvelope) -> dict[str, Any]:
    metadata = dict(envelope.message.metadata or {})
    if envelope.notification_type == "chat":
        chat_id = metadata.get("chat_id")
        if chat_id is None:
            raise RuntimeError("External chat notification is missing chat_id metadata")
        return {"event_type": envelope.event_type, "chat_id": str(chat_id)}
    payload = {
        "event_type": envelope.event_type,
        "sender_id": envelope.sender.user_id,
        "sender_name": envelope.sender.display_name,
        "summary": envelope.message.content,
    }
    payload.update(metadata)
    return payload


def _transport_payload(transport: agent_runtime_protocol.AgentRuntimeTransport) -> dict[str, str]:
    payload: dict[str, str] = {}
    if transport.delivery_id is not None:
        payload["delivery_id"] = transport.delivery_id
    if transport.correlation_id is not None:
        payload["correlation_id"] = transport.correlation_id
    if transport.idempotency_key is not None:
        payload["idempotency_key"] = transport.idempotency_key
    return payload
