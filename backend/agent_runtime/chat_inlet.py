"""Chat delivery inlet from messaging into Agent Runtime."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from backend.agent_runtime.chat_notification_format import format_chat_notification
from backend.agent_runtime.port import get_agent_runtime_gateway
from backend.protocols.agent_runtime import (
    AgentChatContext,
    AgentChatDeliveryEnvelope,
    AgentChatRecipient,
    AgentRuntimeActor,
    AgentRuntimeMessage,
)
from messaging.delivery.contracts import ChatDeliveryRequest

logger = logging.getLogger(__name__)


def make_chat_delivery_fn(app: Any):
    """Create a delivery callback for MessagingService."""
    import asyncio

    loop = asyncio.get_running_loop()
    logger.info("[delivery] make_chat_delivery_fn: loop=%s", loop)

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
        envelope = AgentChatDeliveryEnvelope(
            chat=AgentChatContext(chat_id=request.chat_id),
            sender=AgentRuntimeActor(
                user_id=request.sender_id,
                user_type=request.sender_type,
                display_name=request.sender_name,
                avatar_url=request.sender_avatar_url,
                source="chat",
            ),
            recipient=AgentChatRecipient(agent_user_id=request.recipient_id, runtime_source="mycel"),
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

    def _deliver(request: ChatDeliveryRequest) -> None:
        logger.info("[delivery] _deliver called: recipient=%s", request.recipient_id)
        future = asyncio.run_coroutine_threadsafe(deliver_to_runtime_gateway(request), loop)
        future.result()
        logger.info("[delivery] async delivery completed for %s", request.recipient_id)

    return _deliver
