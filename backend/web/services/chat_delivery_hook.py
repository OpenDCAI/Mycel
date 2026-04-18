"""Chat delivery hook for the Agent Runtime Gateway."""

from __future__ import annotations

import functools
import logging
from enum import Enum
from typing import Any

from backend.protocols.agent_runtime import (
    AgentChatActor,
    AgentChatContext,
    AgentChatDeliveryEnvelope,
    AgentChatMessage,
    AgentChatRecipient,
)
from backend.web.services.agent_runtime_port import get_agent_runtime_gateway
from storage.contracts import UserRow

logger = logging.getLogger(__name__)


def make_chat_delivery_fn(app: Any):
    """Create a delivery callback for MessagingService."""
    import asyncio

    loop = asyncio.get_running_loop()
    logger.info("[delivery] make_chat_delivery_fn: loop=%s", loop)

    async def deliver_to_runtime_gateway(
        recipient_id: str,
        recipient_user: UserRow,
        content: str,
        sender_name: str,
        chat_id: str,
        sender_id: str,
        sender_avatar_url: str | None = None,
        signal: str | None = None,
    ) -> None:
        raw_recipient_type = getattr(recipient_user, "type", "agent")
        recipient_type = raw_recipient_type.value if isinstance(raw_recipient_type, Enum) else str(raw_recipient_type)
        envelope = AgentChatDeliveryEnvelope(
            chat=AgentChatContext(chat_id=chat_id),
            sender=AgentChatActor(
                user_id=sender_id,
                user_type="unknown",
                display_name=sender_name,
                avatar_url=sender_avatar_url,
            ),
            recipient=AgentChatRecipient(agent_user_id=recipient_id, runtime_source="mycel"),
            message=AgentChatMessage(content=content, signal=signal),
            extensions={
                "mycel": {
                    "recipient_user_id": getattr(recipient_user, "id", recipient_id),
                    "recipient_user_type": recipient_type,
                }
            },
        )
        await get_agent_runtime_gateway(app).dispatch_chat(envelope)

    def _deliver(
        recipient_id: str,
        recipient_user: UserRow,
        content: str,
        sender_name: str,
        chat_id: str,
        sender_id: str,
        sender_avatar_url: str | None = None,
        signal: str | None = None,
    ) -> None:
        logger.info("[delivery] _deliver called: recipient=%s user=%s", recipient_id, recipient_user.id)
        future = asyncio.run_coroutine_threadsafe(
            deliver_to_runtime_gateway(
                recipient_id,
                recipient_user,
                content,
                sender_name,
                chat_id,
                sender_id,
                sender_avatar_url,
                signal=signal,
            ),
            loop,
        )

        future.add_done_callback(functools.partial(_log_delivery_result, recipient_id))

    return _deliver


def _log_delivery_result(recipient_id: str, f: Any) -> None:
    """Done-callback for async delivery futures."""
    exc = f.exception()
    if exc:
        logger.error("[delivery] async delivery failed for %s: %s", recipient_id, exc, exc_info=exc)
    else:
        logger.info("[delivery] async delivery completed for %s", recipient_id)
