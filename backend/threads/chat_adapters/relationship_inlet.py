from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any

from backend.identity.avatar.urls import avatar_url
from backend.threads.chat_adapters.port import get_agent_runtime_gateway
from messaging.contracts import RelationshipEvent, RelationshipRow
from messaging.delivery.runtime_thread_selector import select_runtime_thread_for_recipient
from protocols.agent_runtime import AgentRuntimeActor, AgentRuntimeMessage, AgentThreadInputEnvelope

_DECISION_VERBS: dict[RelationshipEvent, str] = {
    "approve": "approved",
    "reject": "rejected",
}


def make_relationship_request_notification_fn(app: Any, *, activity_reader: Any, thread_repo: Any, user_repo: Any):
    if activity_reader is None:
        raise RuntimeError("Agent runtime thread activity reader is not configured")
    loop = asyncio.get_running_loop()

    async def notify_runtime(row: RelationshipRow) -> None:
        requester_id = _requester_id(row)
        target_id = _target_id(row, requester_id)
        requester = _require_user(user_repo, requester_id, "requester")
        target = _require_user(user_repo, target_id, "target")
        if _user_type(target, target_id) != "agent":
            return

        thread_id = select_runtime_thread_for_recipient(
            target_id,
            thread_repo=thread_repo,
            activity_reader=activity_reader,
        )
        if thread_id is None:
            raise RuntimeError(f"Relationship request target agent has no runtime thread: {target_id}")

        await get_agent_runtime_gateway(app).dispatch_thread_input(
            AgentThreadInputEnvelope(
                thread_id=thread_id,
                sender=AgentRuntimeActor(
                    user_id=requester_id,
                    user_type=_user_type(requester, requester_id),
                    display_name=_display_name(requester, requester_id),
                    avatar_url=avatar_url(requester_id, bool(getattr(requester, "avatar", None))),
                    source="relationship",
                ),
                message=AgentRuntimeMessage(
                    content=_notification_content(
                        _display_name(requester, requester_id),
                        row.message,
                    ),
                    metadata={"relationship_id": row.id},
                ),
            )
        )

    def _notify(row: RelationshipRow) -> None:
        future = asyncio.run_coroutine_threadsafe(notify_runtime(row), loop)
        future.result()

    return _notify


def make_relationship_decision_notification_fn(app: Any, *, activity_reader: Any, thread_repo: Any, user_repo: Any):
    if activity_reader is None:
        raise RuntimeError("Agent runtime thread activity reader is not configured")
    loop = asyncio.get_running_loop()

    async def notify_runtime(row: RelationshipRow, event: RelationshipEvent) -> None:
        requester_id = _requester_id(row)
        decider_id = _target_id(row, requester_id)
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
            raise RuntimeError(f"Relationship decision requester agent has no runtime thread: {requester_id}")

        await get_agent_runtime_gateway(app).dispatch_thread_input(
            AgentThreadInputEnvelope(
                thread_id=thread_id,
                sender=AgentRuntimeActor(
                    user_id=decider_id,
                    user_type=_user_type(decider, decider_id),
                    display_name=_display_name(decider, decider_id),
                    avatar_url=avatar_url(decider_id, bool(getattr(decider, "avatar", None))),
                    source="relationship",
                ),
                message=AgentRuntimeMessage(
                    content=f"{_display_name(decider, decider_id)} {_decision_verb(event)} your relationship request.",
                    metadata={
                        "relationship_id": row.id,
                        "event": event,
                        "state": row.state,
                    },
                ),
            )
        )

    def _notify(row: RelationshipRow, event: RelationshipEvent) -> None:
        future = asyncio.run_coroutine_threadsafe(notify_runtime(row, event), loop)
        future.result()

    return _notify


def _requester_id(row: RelationshipRow) -> str:
    if row.initiator_user_id is None:
        raise RuntimeError(f"Relationship request row is missing initiator: {row.id}")
    return row.initiator_user_id


def _target_id(row: RelationshipRow, requester_id: str) -> str:
    if requester_id == row.user_low:
        return row.user_high
    if requester_id == row.user_high:
        return row.user_low
    raise RuntimeError(f"Relationship request initiator is not a party: {row.id}")


def _require_user(user_repo: Any, user_id: str, role: str) -> Any:
    user = user_repo.get_by_id(user_id)
    if user is None:
        raise RuntimeError(f"Relationship request {role} user not found: {user_id}")
    return user


def _user_type(user: Any, user_id: str) -> str:
    raw_type = getattr(user, "type", None)
    if raw_type is None:
        raise RuntimeError(f"Relationship request user is missing type: {user_id}")
    return raw_type.value if isinstance(raw_type, Enum) else str(raw_type)


def _display_name(user: Any, user_id: str) -> str:
    display_name = getattr(user, "display_name", None)
    if display_name is None:
        raise RuntimeError(f"Relationship request user is missing display name: {user_id}")
    return str(display_name)


def _notification_content(requester_name: str, message: str | None) -> str:
    base = f"{requester_name} requested a relationship with you."
    if message and message.strip():
        base = f"{base} Message: {message.strip()}"
    return f"{base} Review the pending relationship request in Mycel, then approve or reject it."


def _decision_verb(event: RelationshipEvent) -> str:
    try:
        return _DECISION_VERBS[event]
    except KeyError as exc:
        raise RuntimeError(f"Relationship decision notification does not support event: {event}") from exc
