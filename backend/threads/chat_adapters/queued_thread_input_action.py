from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
