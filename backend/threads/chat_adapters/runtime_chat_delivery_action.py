from __future__ import annotations

from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass
from typing import Any

from backend.threads.chat_adapters.port import get_agent_runtime_gateway
from backend.threads.chat_adapters.runtime_event_hook import RuntimeEventActionRoute
from backend.threads.chat_adapters.runtime_identity import runtime_actor
from backend.threads.chat_adapters.runtime_recipient import resolve_runtime_chat_delivery_recipient
from protocols.agent_runtime import (
    AgentChatContext,
    AgentChatDeliveryEnvelope,
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


def make_runtime_chat_delivery_event_hook[EventT](
    app: Any,
    planner: Callable[[EventT], Iterable[RuntimeChatDeliveryAction]],
    *,
    thread_repo: Any,
    activity_reader: Any,
) -> Callable[[EventT], None]:
    return RuntimeEventActionRoute(
        planner=planner,
        dispatch_actions=runtime_chat_delivery_action_dispatcher(
            app,
            thread_repo=thread_repo,
            activity_reader=activity_reader,
        ),
    ).sync_hook()


async def dispatch_runtime_chat_delivery_actions(
    app: Any,
    actions: Iterable[RuntimeChatDeliveryAction],
    *,
    thread_repo: Any,
    activity_reader: Any,
) -> int:
    gateway = get_agent_runtime_gateway(app)
    dispatched_count = 0
    for action in actions:
        envelope = plan_runtime_chat_delivery_envelope(
            action,
            thread_repo=thread_repo,
            activity_reader=activity_reader,
        )
        if envelope is None:
            continue
        await gateway.dispatch_chat(envelope)
        dispatched_count += 1
    return dispatched_count


def runtime_chat_delivery_action_dispatcher(
    app: Any,
    *,
    thread_repo: Any,
    activity_reader: Any,
) -> Callable[[list[RuntimeChatDeliveryAction]], Coroutine[Any, Any, int]]:
    async def dispatch_actions(actions: list[RuntimeChatDeliveryAction]) -> int:
        return await dispatch_runtime_chat_delivery_actions(
            app,
            actions,
            thread_repo=thread_repo,
            activity_reader=activity_reader,
        )

    return dispatch_actions


def plan_runtime_chat_delivery_envelope(
    action: RuntimeChatDeliveryAction,
    *,
    thread_repo: Any,
    activity_reader: Any,
) -> AgentChatDeliveryEnvelope | None:
    recipient = resolve_runtime_chat_delivery_recipient(
        action.recipient_id,
        action.recipient_user_type,
        thread_repo=thread_repo,
        activity_reader=activity_reader,
    )
    if recipient is None:
        return None
    return AgentChatDeliveryEnvelope(
        chat=AgentChatContext(chat_id=action.chat_id),
        sender=runtime_actor(
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
