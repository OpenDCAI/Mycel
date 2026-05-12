from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any

from backend.threads.chat_adapters.chat_notification_format import format_chat_notification
from backend.threads.chat_adapters.runtime_chat_delivery_action import (
    RuntimeChatDeliveryAction,
    make_runtime_chat_delivery_event_hook,
)
from messaging.delivery.contracts import ChatDeliveryRequest


def make_chat_delivery_fn(app: Any, *, activity_reader: Any, thread_repo: Any):
    return make_runtime_chat_delivery_event_hook(
        app,
        chat_delivery_runtime_action_planner(),
        thread_repo=thread_repo,
        activity_reader=activity_reader,
    )


def chat_delivery_runtime_action_planner() -> Callable[[ChatDeliveryRequest], list[RuntimeChatDeliveryAction]]:
    def plan(request: ChatDeliveryRequest) -> list[RuntimeChatDeliveryAction]:
        return [chat_delivery_runtime_action(request)]

    return plan


def chat_delivery_runtime_action(request: ChatDeliveryRequest) -> RuntimeChatDeliveryAction:
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
    return RuntimeChatDeliveryAction(
        chat_id=request.chat_id,
        recipient_id=request.recipient_id,
        recipient_user_id=recipient_user_id,
        recipient_user_type=recipient_type,
        sender_id=request.sender_id,
        sender_type=request.sender_type,
        sender_name=request.sender_name,
        sender_avatar_url=request.sender_avatar_url,
        content=rendered_content,
        raw_content=request.content,
        signal=request.signal,
    )
