from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any

from backend.identity.avatar.urls import avatar_url
from backend.threads.chat_adapters.port import get_agent_runtime_gateway
from messaging.delivery.runtime_thread_selector import select_runtime_thread_for_recipient
from protocols.agent_runtime import AgentRuntimeActor, AgentRuntimeMessage, AgentThreadInputEnvelope


def make_chat_join_rejection_notification_fn(app: Any, *, activity_reader: Any, thread_repo: Any, user_repo: Any):
    if activity_reader is None:
        raise RuntimeError("Agent runtime thread activity reader is not configured")
    loop = asyncio.get_running_loop()

    async def notify_runtime(row: dict[str, Any]) -> None:
        requester_id = _required_str(row, "requester_user_id")
        decider_id = _required_str(row, "decided_by_user_id")
        chat_id = _required_str(row, "chat_id")
        requester = _require_user(user_repo, requester_id, "requester")
        decider = _require_user(user_repo, decider_id, "decider")
        if _user_type(requester, requester_id) != "agent":
            return

        thread_id = select_runtime_thread_for_recipient(
            requester_id,
            thread_repo=thread_repo,
            activity_reader=activity_reader,
        )
        if thread_id is None:
            raise RuntimeError(f"Chat join request requester agent has no runtime thread: {requester_id}")

        await get_agent_runtime_gateway(app).dispatch_thread_input(
            AgentThreadInputEnvelope(
                thread_id=thread_id,
                sender=AgentRuntimeActor(
                    user_id=decider_id,
                    user_type=_user_type(decider, decider_id),
                    display_name=_display_name(decider, decider_id),
                    avatar_url=avatar_url(decider_id, bool(getattr(decider, "avatar", None))),
                    source="chat_join",
                ),
                message=AgentRuntimeMessage(
                    content=f"{_display_name(decider, decider_id)} rejected your request to join chat {chat_id}.",
                    metadata={
                        "chat_join_request_id": _required_str(row, "id"),
                        "chat_id": chat_id,
                        "state": "rejected",
                    },
                ),
            )
        )

    def _notify(row: dict[str, Any]) -> None:
        future = asyncio.run_coroutine_threadsafe(notify_runtime(row), loop)
        future.result()

    return _notify


def _required_str(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not value:
        raise RuntimeError(f"Chat join rejection row is missing {key}: {row.get('id') or '<missing>'}")
    return str(value)


def _require_user(user_repo: Any, user_id: str, role: str) -> Any:
    user = user_repo.get_by_id(user_id)
    if user is None:
        raise RuntimeError(f"Chat join rejection {role} user not found: {user_id}")
    return user


def _user_type(user: Any, user_id: str) -> str:
    raw_type = getattr(user, "type", None)
    if raw_type is None:
        raise RuntimeError(f"Chat join rejection user is missing type: {user_id}")
    return raw_type.value if isinstance(raw_type, Enum) else str(raw_type)


def _display_name(user: Any, user_id: str) -> str:
    display_name = getattr(user, "display_name", None)
    if display_name is None:
        raise RuntimeError(f"Chat join rejection user is missing display name: {user_id}")
    return str(display_name)
