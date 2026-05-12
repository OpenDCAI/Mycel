from __future__ import annotations

from typing import Any

from backend.threads.chat_adapters.port import get_agent_runtime_gateway
from backend.threads.chat_adapters.runtime_event_hook import make_sync_runtime_event_hook
from backend.threads.chat_adapters.runtime_identity import display_name, make_runtime_actor, require_user, user_type
from backend.threads.chat_adapters.runtime_recipient import select_runtime_notification_recipient
from protocols.agent_runtime import (
    AgentRuntimeMessage,
    AgentRuntimeNotificationEnvelope,
)


def make_chat_join_rejection_notification_fn(app: Any, *, activity_reader: Any, thread_repo: Any, user_repo: Any):
    async def notify_runtime(row: dict[str, Any]) -> None:
        requester_id = _required_str(row, "requester_user_id")
        decider_id = _required_str(row, "decided_by_user_id")
        chat_id = _required_str(row, "chat_id")
        requester = require_user(user_repo, requester_id, context="Chat join rejection", role="requester")
        decider = require_user(user_repo, decider_id, context="Chat join rejection", role="decider")
        requester_type = user_type(requester, requester_id, context="Chat join rejection")
        content = f"{display_name(decider, decider_id, context='Chat join rejection')} rejected your request to join chat {chat_id}."
        metadata = {
            "chat_join_request_id": _required_str(row, "id"),
            "chat_id": chat_id,
            "state": "rejected",
        }
        recipient = select_runtime_notification_recipient(
            requester_id,
            requester_type,
            thread_repo=thread_repo,
            activity_reader=activity_reader,
            context="chat join",
        )
        if recipient is None:
            return
        await get_agent_runtime_gateway(app).dispatch_notification(
            AgentRuntimeNotificationEnvelope(
                event_type="chat.join.rejected",
                recipient=recipient,
                sender=make_runtime_actor(
                    user_id=decider_id,
                    user=decider,
                    source="chat_join",
                    context="Chat join rejection",
                    include_avatar=True,
                ),
                message=AgentRuntimeMessage(
                    content=content,
                    metadata=metadata,
                ),
                notification_type="chat_join",
            )
        )

    return make_sync_runtime_event_hook(notify_runtime)


def _required_str(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not value:
        raise RuntimeError(f"Chat join rejection row is missing {key}: {row.get('id') or '<missing>'}")
    return str(value)
