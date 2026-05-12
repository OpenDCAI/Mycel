from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.threads.chat_adapters.runtime_event_hook import make_sync_runtime_event_hook
from backend.threads.chat_adapters.runtime_identity import display_name, require_user
from backend.threads.chat_adapters.runtime_notification_action import (
    RuntimeNotificationAction,
    dispatch_runtime_notification_actions,
)
from core.event_actions import plan_event_actions, single_event_action_planner


def make_chat_join_rejection_notification_fn(app: Any, *, activity_reader: Any, thread_repo: Any, user_repo: Any):
    planner = chat_join_rejection_notification_action_planner(user_repo)

    async def notify_runtime(row: dict[str, Any]) -> None:
        actions = plan_event_actions([planner], row)
        await dispatch_runtime_notification_actions(
            app,
            actions,
            user_repo=user_repo,
            thread_repo=thread_repo,
            activity_reader=activity_reader,
        )

    return make_sync_runtime_event_hook(notify_runtime)


def chat_join_rejection_notification_action_planner(user_repo: Any) -> Callable[[dict[str, Any]], list[RuntimeNotificationAction]]:
    def make_action(row: dict[str, Any]) -> RuntimeNotificationAction:
        return chat_join_rejection_notification_action(row, user_repo=user_repo)

    return single_event_action_planner(make_action)


def chat_join_rejection_notification_action(row: dict[str, Any], *, user_repo: Any) -> RuntimeNotificationAction:
    requester_id = _required_str(row, "requester_user_id")
    decider_id = _required_str(row, "decided_by_user_id")
    chat_id = _required_str(row, "chat_id")
    decider = require_user(user_repo, decider_id, context="Chat join rejection", role="decider")
    return RuntimeNotificationAction(
        context="Chat join rejection",
        recipient_user_id=requester_id,
        sender_user_id=decider_id,
        sender_source="chat_join",
        event_type="chat.join.rejected",
        notification_type="chat_join",
        content=f"{display_name(decider, decider_id, context='Chat join rejection')} rejected your request to join chat {chat_id}.",
        metadata={
            "chat_join_request_id": _required_str(row, "id"),
            "chat_id": chat_id,
            "state": "rejected",
        },
        include_sender_avatar=True,
    )


def _required_str(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not value:
        raise RuntimeError(f"Chat join rejection row is missing {key}: {row.get('id') or '<missing>'}")
    return str(value)
