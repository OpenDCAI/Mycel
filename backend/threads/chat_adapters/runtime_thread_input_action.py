from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.threads.chat_adapters.runtime_identity import runtime_actor
from protocols.agent_runtime import AgentRuntimeMessage, AgentThreadInputEnvelope


@dataclass(frozen=True)
class RuntimeThreadInputAction:
    thread_id: str
    sender_user_id: str
    sender_user_type: str
    sender_display_name: str
    sender_source: str
    content: str
    attachments: list[str] | None = None
    metadata: dict[str, Any] | None = None
    enable_trajectory: bool = False


@dataclass(frozen=True)
class QueuedThreadInputAction:
    thread_id: str
    content: str
    notification_type: str = "steer"


def queued_thread_input_action(*, thread_id: str, message: str) -> QueuedThreadInputAction:
    return QueuedThreadInputAction(thread_id=thread_id, content=message)


def queued_command_thread_input_action(*, thread_id: str, message: str) -> QueuedThreadInputAction:
    return QueuedThreadInputAction(thread_id=thread_id, content=message, notification_type="command")


def dispatch_queued_thread_input_action(queue_manager: Any, action: QueuedThreadInputAction) -> dict[str, str]:
    queue_manager.enqueue(action.content, action.thread_id, notification_type=action.notification_type)
    return {"status": "queued", "thread_id": action.thread_id}


def owner_runtime_thread_input_action(
    *,
    thread_id: str,
    user_id: str,
    message: str,
    attachments: list[str] | None,
    enable_trajectory: bool,
) -> RuntimeThreadInputAction:
    return RuntimeThreadInputAction(
        thread_id=thread_id,
        sender_user_id=user_id,
        sender_user_type="human",
        sender_display_name="Owner",
        sender_source="owner",
        content=message,
        attachments=attachments,
        enable_trajectory=enable_trajectory,
    )


def internal_runtime_thread_input_action(
    *,
    thread_id: str,
    user_id: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> RuntimeThreadInputAction:
    return RuntimeThreadInputAction(
        thread_id=thread_id,
        sender_user_id=user_id,
        sender_user_type="system",
        sender_display_name="Internal",
        sender_source="internal",
        content=message,
        metadata=metadata,
    )


def plan_runtime_thread_input_envelope(action: RuntimeThreadInputAction) -> AgentThreadInputEnvelope:
    return AgentThreadInputEnvelope(
        thread_id=action.thread_id,
        sender=runtime_actor(
            user_id=action.sender_user_id,
            user_type=action.sender_user_type,
            display_name=action.sender_display_name,
            source=action.sender_source,
        ),
        message=AgentRuntimeMessage(
            content=action.content,
            attachments=action.attachments,
            metadata=action.metadata,
        ),
        enable_trajectory=action.enable_trajectory,
    )
