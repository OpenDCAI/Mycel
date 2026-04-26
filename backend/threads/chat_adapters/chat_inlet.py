from __future__ import annotations

from enum import Enum
from typing import Any

from backend.threads.chat_adapters.chat_notification_format import format_chat_notification
from backend.threads.chat_adapters.port import get_agent_runtime_gateway
from messaging.delivery.contracts import ChatDeliveryRequest
from messaging.delivery.runtime_thread_selector import select_runtime_thread_for_recipient
from protocols.agent_runtime import (
    AgentChatContext,
    AgentChatDeliveryEnvelope,
    AgentChatRecipient,
    AgentRuntimeActor,
    AgentRuntimeMessage,
)


def make_chat_delivery_fn(app: Any, *, activity_reader: Any, thread_repo: Any):
    import asyncio

    if activity_reader is None:
        raise RuntimeError("Agent runtime thread activity reader is not configured")
    loop = asyncio.get_running_loop()

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
        if recipient_type == "external":
            runtime_source = "external"
            thread_id = None
        elif recipient_type == "agent":
            runtime_source = "mycel"
            thread_id = select_runtime_thread_for_recipient(
                request.recipient_id,
                thread_repo=thread_repo,
                activity_reader=activity_reader,
            )
            if thread_id is None:
                raise RuntimeError(f"Agent chat recipient has no runtime thread: {request.recipient_id}")
        else:
            raise RuntimeError(f"Chat delivery recipient type is not runtime-addressable: {recipient_type}")
        envelope = AgentChatDeliveryEnvelope(
            chat=AgentChatContext(chat_id=request.chat_id),
            sender=AgentRuntimeActor(
                user_id=request.sender_id,
                user_type=request.sender_type,
                display_name=request.sender_name,
                avatar_url=request.sender_avatar_url,
                source="chat",
            ),
            recipient=AgentChatRecipient(agent_user_id=request.recipient_id, runtime_source=runtime_source, thread_id=thread_id),
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
        future = asyncio.run_coroutine_threadsafe(deliver_to_runtime_gateway(request), loop)
        future.result()

    return _deliver
