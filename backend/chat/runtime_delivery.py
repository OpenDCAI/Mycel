"""Chat-owned delivery hook into an Agent Runtime transport."""

from __future__ import annotations

import logging
from enum import Enum

from messaging.delivery.contracts import ChatDeliveryRequest
from protocols.agent_runtime import (
    AgentChatContext,
    AgentChatDeliveryEnvelope,
    AgentChatRecipient,
    AgentRuntimeActor,
    AgentRuntimeMessage,
    ChatDeliveryTransport,
)

logger = logging.getLogger(__name__)


def format_chat_notification(sender_name: str, chat_id: str, unread_count: int, signal: str | None = None) -> str:
    """Lightweight notification — agent must read_messages to see content.

    @@@v3-notification-only - no message content injected. Agent calls
    read_messages(chat_id=...) to read, then send_message() to reply.
    """
    signal_hint = f" [signal: {signal}]" if signal and signal != "open" else ""
    return (
        "<system-reminder>\n"
        f"New message from {sender_name} in chat {chat_id} ({unread_count} unread).{signal_hint}\n"
        f'Read it with read_messages(chat_id="{chat_id}").\n'
        f'Do not call send_message(chat_id="{chat_id}", ...) before read_messages(chat_id="{chat_id}") succeeds.\n'
        f'Reply with send_message(chat_id="{chat_id}", content="...").\n'
        "Prefer using this exact chat_id directly.\n"
        "Do not treat your normal assistant text as a chat reply.\n"
        "</system-reminder>"
    )


def make_chat_delivery_fn(
    *,
    transport: ChatDeliveryTransport,
):
    """Create a delivery callback that targets an injected runtime transport."""
    if transport is None:
        raise RuntimeError("Chat runtime transport is not configured")
    logger.info("[delivery] make_chat_delivery_fn")

    def _deliver(request: ChatDeliveryRequest) -> None:
        raw_recipient_type = getattr(request.recipient_user, "type", None)
        if raw_recipient_type is None:
            raise RuntimeError(f"Chat delivery recipient is missing user type: {request.recipient_id}")
        recipient_type = raw_recipient_type.value if isinstance(raw_recipient_type, Enum) else str(raw_recipient_type)
        recipient_user_id = getattr(request.recipient_user, "id", None)
        if recipient_user_id is None:
            raise RuntimeError(f"Chat delivery recipient is missing user id: {request.recipient_id}")
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
        logger.info("[delivery] _deliver called: recipient=%s", request.recipient_id)
        transport.deliver_chat(envelope)
        logger.info("[delivery] async delivery completed for %s", request.recipient_id)

    return _deliver
