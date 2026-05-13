from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from backend.threads.chat_adapters.chat_notification_format import format_chat_notification
from backend.threads.chat_adapters.runtime_notification_action import RuntimeNotificationAction, make_runtime_notification_event_hook
from messaging.delivery.contracts import ChatDeliveryRequest


def make_chat_delivery_fn(app: Any, *, activity_reader: Any, thread_repo: Any, user_repo: Any):
    return make_runtime_notification_event_hook(
        app,
        chat_delivery_runtime_notification_actions,
        thread_repo=thread_repo,
        activity_reader=activity_reader,
        user_repo=user_repo,
    )


def chat_delivery_runtime_notification_actions(request: ChatDeliveryRequest) -> Iterable[RuntimeNotificationAction]:
    yield RuntimeNotificationAction(
        context="Chat delivery",
        recipient_user_id=request.recipient_id,
        sender_user_id=request.sender_id,
        sender_source="chat",
        event_type="chat.message",
        notification_type="chat",
        content=format_chat_notification(
            request.sender_name,
            request.chat_id,
            request.unread_count,
            signal=request.signal,
        ),
        signal=request.signal,
        metadata={
            "chat_id": request.chat_id,
            "recipient_user_id": request.recipient_id,
            "raw_content": request.content,
        },
    )
