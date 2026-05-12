from __future__ import annotations

from typing import Any

from protocols import agent_runtime as agent_runtime_protocol

from .runtime_metadata import notification_message_metadata


class NativeAgentNotificationHandler:
    def __init__(self, *, thread_input_handler: Any) -> None:
        self._thread_input_handler = thread_input_handler

    async def dispatch_notification(
        self, envelope: agent_runtime_protocol.AgentRuntimeNotificationEnvelope
    ) -> agent_runtime_protocol.AgentRuntimeNotificationResult:
        thread_id = envelope.recipient.thread_id
        if not thread_id:
            raise RuntimeError(f"Agent runtime notification recipient has no runtime thread: {envelope.recipient.agent_user_id}")
        result = await self._thread_input_handler.dispatch(
            agent_runtime_protocol.AgentThreadInputEnvelope(
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
        )
        return agent_runtime_protocol.AgentRuntimeNotificationResult(status="accepted", thread_id=result.thread_id)
