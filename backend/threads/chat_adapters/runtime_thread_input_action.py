from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.threads.chat_adapters.port import get_agent_runtime_gateway
from protocols.agent_runtime import AgentRuntimeActor, AgentRuntimeMessage, AgentThreadInputEnvelope


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


async def dispatch_runtime_thread_input_action(app: Any, action: RuntimeThreadInputAction):
    return await get_agent_runtime_gateway(app).dispatch_thread_input(
        AgentThreadInputEnvelope(
            thread_id=action.thread_id,
            sender=AgentRuntimeActor(
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
    )
