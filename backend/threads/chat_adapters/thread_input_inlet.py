from __future__ import annotations

from typing import Any

from backend.threads.chat_adapters.runtime_action import dispatch_runtime_action
from backend.threads.chat_adapters.runtime_thread_input_action import (
    RuntimeThreadInputAction,
    dispatch_queued_thread_input_action,
    internal_runtime_thread_input_action,
    owner_runtime_thread_input_action,
    queued_command_thread_input_action,
    queued_thread_input_action,
)
from protocols.agent_runtime import AgentThreadInputResult


async def dispatch_owner_thread_input(
    app: Any,
    *,
    thread_id: str,
    user_id: str,
    message: str,
    attachments: list[str] | None,
    enable_trajectory: bool,
) -> AgentThreadInputResult:
    return await _dispatch_thread_input_action(
        app,
        action=owner_runtime_thread_input_action(
            thread_id=thread_id,
            user_id=user_id,
            message=message,
            attachments=attachments,
            enable_trajectory=enable_trajectory,
        ),
    )


async def dispatch_internal_thread_input(
    app: Any,
    *,
    thread_id: str,
    user_id: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> AgentThreadInputResult:
    return await _dispatch_thread_input_action(
        app,
        action=internal_runtime_thread_input_action(
            thread_id=thread_id,
            user_id=user_id,
            message=message,
            metadata=metadata,
        ),
    )


async def _dispatch_thread_input_action(app: Any, *, action: RuntimeThreadInputAction) -> AgentThreadInputResult:
    result = await dispatch_runtime_action(app, action)
    if not isinstance(result, AgentThreadInputResult):
        raise RuntimeError("Runtime thread input action did not return a thread input result")
    return result


def queue_thread_input(queue_manager: Any, *, thread_id: str, message: str) -> dict[str, str]:
    return dispatch_queued_thread_input_action(
        queue_manager,
        queued_thread_input_action(thread_id=thread_id, message=message),
    )


def queue_command_thread_input(queue_manager: Any, *, thread_id: str, message: str) -> dict[str, str]:
    return dispatch_queued_thread_input_action(
        queue_manager,
        queued_command_thread_input_action(thread_id=thread_id, message=message),
    )


def requeue_thread_input_item(queue_manager: Any, *, thread_id: str, item: Any) -> None:
    queue_manager.enqueue(
        item.content,
        thread_id,
        notification_type=item.notification_type,
        source=item.source,
        sender_id=item.sender_id,
        sender_name=item.sender_name,
        sender_avatar_url=item.sender_avatar_url,
        is_steer=item.is_steer,
        metadata=item.metadata,
    )
