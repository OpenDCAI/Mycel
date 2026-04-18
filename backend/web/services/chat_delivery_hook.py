"""Chat delivery hook for the Agent Runtime Gateway."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from backend.protocols.agent_runtime import (
    AgentChatContext,
    AgentChatDeliveryEnvelope,
    AgentChatRecipient,
    AgentRuntimeActor,
    AgentRuntimeMessage,
)
from backend.web.services.agent_runtime_port import get_agent_runtime_gateway
from messaging.delivery.dispatcher import ChatDeliveryRequest

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
        envelope = AgentChatDeliveryEnvelope(
            chat=AgentChatContext(chat_id=request.chat_id),
            sender=AgentRuntimeActor(
                user_id=request.sender_id,
                user_type="unknown",
                display_name=request.sender_name,
                avatar_url=request.sender_avatar_url,
                source="chat",
            ),
            recipient=AgentChatRecipient(agent_user_id=request.recipient_id, runtime_source="mycel"),
            message=AgentRuntimeMessage(content=request.content, signal=request.signal),
            extensions={
                "mycel": {
                    "recipient_user_id": getattr(request.recipient_user, "id", request.recipient_id),
                    "recipient_user_type": recipient_type,
                }
            },
        )
        await get_agent_runtime_gateway(app).dispatch_chat(envelope)

    def _deliver(request: ChatDeliveryRequest) -> None:
        logger.info("[delivery] _deliver called: recipient=%s user=%s", request.recipient_id, request.recipient_user.id)
        future = asyncio.run_coroutine_threadsafe(
            deliver_to_runtime_gateway(request),
            loop,
        )
        future.result()
        logger.info("[delivery] async delivery completed for %s", request.recipient_id)

    return _deliver
