from __future__ import annotations

from enum import Enum
from typing import Any

from backend.threads.chat_adapters.chat_notification_format import format_chat_notification
from backend.threads.chat_adapters.port import get_agent_runtime_gateway
from backend.threads.chat_adapters.runtime_event_hook import make_sync_runtime_event_hook
from backend.threads.chat_adapters.runtime_recipient import resolve_runtime_chat_delivery_recipient
from messaging.delivery.contracts import ChatDeliveryRequest
from protocols.agent_runtime import (
    AgentChatContext,
    AgentChatDeliveryEnvelope,
    AgentRuntimeActor,
    AgentRuntimeMessage,
)


def make_chat_delivery_fn(app: Any, *, activity_reader: Any, thread_repo: Any):
    async def deliver_to_runtime_gateway(request: ChatDeliveryRequest) -> None:
        raw_recipient_type = getattr(request.recipient_user, "type", None)
        if raw_recipient_type is None:
            raise RuntimeError(f"Chat delivery recipient is missing user type: {request.recipient_id}")
        recipient_type = raw_recipient_type.value if isinstance(raw_recipient_type, Enum) else str(raw_recipient_type)
        recipient_user_id = getattr(request.recipient_user, "id", None)
        if recipient_user_id is None:
            raise RuntimeError(f"Chat delivery recipient is missing user id: {request.recipient_id}")
        # @@@chat-rendered-content - runtime handlers should enqueue the already rendered
        # chat reminder content; chat-specific unread/rendering belongs on the upstream delivery path.
        rendered_content = format_chat_notification(
            request.sender_name,
            request.chat_id,
            request.unread_count,
            signal=request.signal,
        )
        recipient = resolve_runtime_chat_delivery_recipient(
            request.recipient_id,
            recipient_type,
            thread_repo=thread_repo,
            activity_reader=activity_reader,
        )
        if recipient is None:
            return
        envelope = AgentChatDeliveryEnvelope(
            chat=AgentChatContext(chat_id=request.chat_id),
            sender=AgentRuntimeActor(
                user_id=request.sender_id,
                user_type=request.sender_type,
                display_name=request.sender_name,
                avatar_url=request.sender_avatar_url,
                source="chat",
            ),
            recipient=recipient,
            message=AgentRuntimeMessage(content=rendered_content, signal=request.signal),
            extensions={
                "mycel": {
                    "recipient_user_id": recipient_user_id,
                    "recipient_user_type": recipient_type,
                    "raw_content": request.content,
                }
            },
        )
        await get_agent_runtime_gateway(app).dispatch_chat(envelope)

    return make_sync_runtime_event_hook(deliver_to_runtime_gateway)
