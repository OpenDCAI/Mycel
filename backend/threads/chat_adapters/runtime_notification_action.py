from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.threads.chat_adapters.port import get_agent_runtime_gateway
from backend.threads.chat_adapters.runtime_identity import make_runtime_actor, require_user
from backend.threads.chat_adapters.runtime_recipient import resolve_runtime_notification_recipient
from protocols.agent_runtime import (
    AgentRuntimeMessage,
    AgentRuntimeNotificationEnvelope,
    AgentRuntimeTransport,
)


@dataclass(frozen=True)
class RuntimeNotificationAction:
    context: str
    recipient_user_id: str
    sender_user_id: str
    sender_source: str
    event_type: str
    notification_type: str
    content: str
    metadata: dict[str, Any] | None = None
    transport: AgentRuntimeTransport = AgentRuntimeTransport()
    include_sender_avatar: bool = False
    runtime_context: str | None = None


async def dispatch_runtime_notification_action(
    app: Any,
    action: RuntimeNotificationAction,
    *,
    user_repo: Any,
    thread_repo: Any,
    activity_reader: Any,
) -> bool:
    sender_user = require_user(user_repo, action.sender_user_id, context=action.context, role="sender")
    recipient = resolve_runtime_notification_recipient(
        action.recipient_user_id,
        user_repo=user_repo,
        thread_repo=thread_repo,
        activity_reader=activity_reader,
        context=action.context,
        runtime_context=action.runtime_context,
    )
    if recipient is None:
        return False
    await get_agent_runtime_gateway(app).dispatch_notification(
        AgentRuntimeNotificationEnvelope(
            event_type=action.event_type,
            recipient=recipient,
            sender=make_runtime_actor(
                user_id=action.sender_user_id,
                user=sender_user,
                source=action.sender_source,
                context=action.context,
                include_avatar=action.include_sender_avatar,
            ),
            message=AgentRuntimeMessage(
                content=action.content,
                metadata=action.metadata,
            ),
            notification_type=action.notification_type,
            transport=action.transport,
        ),
    )
    return True
