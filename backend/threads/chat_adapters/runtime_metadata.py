from __future__ import annotations

from typing import Any

from protocols import agent_runtime as agent_runtime_protocol


def transport_metadata(transport: agent_runtime_protocol.AgentRuntimeTransport) -> dict[str, str]:
    metadata: dict[str, str] = {}
    if transport.delivery_id is not None:
        metadata["delivery_id"] = transport.delivery_id
    if transport.correlation_id is not None:
        metadata["correlation_id"] = transport.correlation_id
    if transport.idempotency_key is not None:
        metadata["idempotency_key"] = transport.idempotency_key
    return metadata


def notification_message_metadata(envelope: agent_runtime_protocol.AgentRuntimeNotificationEnvelope) -> dict[str, Any]:
    metadata = dict(envelope.message.metadata or {})
    metadata.update(
        {
            "event_type": envelope.event_type,
            "notification_type": envelope.notification_type,
            "runtime_protocol_version": envelope.protocol_version,
        }
    )
    metadata.update(transport_metadata(envelope.transport))
    return metadata


def thread_input_from_notification(
    envelope: agent_runtime_protocol.AgentRuntimeNotificationEnvelope,
) -> agent_runtime_protocol.AgentThreadInputEnvelope:
    thread_id = envelope.recipient.thread_id
    if not thread_id:
        raise RuntimeError(f"Agent runtime notification recipient has no runtime thread: {envelope.recipient.agent_user_id}")
    return agent_runtime_protocol.AgentThreadInputEnvelope(
        thread_id=thread_id,
        sender=envelope.sender,
        message=agent_runtime_protocol.AgentRuntimeMessage(
            content=envelope.message.content,
            content_type=envelope.message.content_type,
            message_id=envelope.message.message_id,
            signal=envelope.message.signal,
            created_at=envelope.message.created_at,
            attachments=envelope.message.attachments,
            metadata=notification_message_metadata(envelope),
        ),
        transport=envelope.transport,
    )


def thread_input_message_metadata(envelope: agent_runtime_protocol.AgentThreadInputEnvelope) -> dict[str, Any]:
    metadata = dict(envelope.message.metadata or {})
    metadata.update(transport_metadata(envelope.transport))
    if envelope.message.attachments:
        metadata["attachments"] = envelope.message.attachments
    return metadata


def thread_input_metadata(envelope: agent_runtime_protocol.AgentThreadInputEnvelope) -> dict[str, Any]:
    metadata = thread_input_message_metadata(envelope)
    metadata.update(
        {
            "source": envelope.sender.source,
            "sender_id": envelope.sender.user_id,
            "sender_name": envelope.sender.display_name,
            "sender_avatar_url": envelope.sender.avatar_url,
        }
    )
    return metadata


def thread_input_notification_type(envelope: agent_runtime_protocol.AgentThreadInputEnvelope) -> str:
    metadata = envelope.message.metadata or {}
    return str(metadata.get("notification_type") or "steer")
