from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.threads.chat_adapters.port import get_agent_runtime_gateway
from backend.threads.chat_adapters.runtime_recipient import resolve_runtime_chat_delivery_recipient
from protocols.agent_runtime import (
    AgentChatContext,
    AgentChatDeliveryEnvelope,
    AgentRuntimeActor,
    AgentRuntimeMessage,
)


@dataclass(frozen=True)
class RuntimeChatDeliveryAction:
    chat_id: str
    recipient_id: str
    recipient_user_id: str
    recipient_user_type: str
    sender_id: str
    sender_type: str
    sender_name: str
    sender_avatar_url: str | None
    content: str
    raw_content: str
    signal: str | None


async def dispatch_runtime_chat_delivery_action(
    app: Any,
    action: RuntimeChatDeliveryAction,
    *,
    thread_repo: Any,
    activity_reader: Any,
) -> bool:
    recipient = resolve_runtime_chat_delivery_recipient(
        action.recipient_id,
        action.recipient_user_type,
        thread_repo=thread_repo,
        activity_reader=activity_reader,
    )
    if recipient is None:
        return False
    await get_agent_runtime_gateway(app).dispatch_chat(
        AgentChatDeliveryEnvelope(
            chat=AgentChatContext(chat_id=action.chat_id),
            sender=AgentRuntimeActor(
                user_id=action.sender_id,
                user_type=action.sender_type,
                display_name=action.sender_name,
                avatar_url=action.sender_avatar_url,
                source="chat",
            ),
            recipient=recipient,
            message=AgentRuntimeMessage(content=action.content, signal=action.signal),
            extensions={
                "mycel": {
                    "recipient_user_id": action.recipient_user_id,
                    "recipient_user_type": action.recipient_user_type,
                    "raw_content": action.raw_content,
                }
            },
        )
    )
    return True
