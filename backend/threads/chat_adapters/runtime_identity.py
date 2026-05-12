from __future__ import annotations

from enum import Enum
from typing import Any

from backend.identity.avatar.urls import avatar_url
from protocols.agent_runtime import AgentRuntimeActor


def require_user(user_repo: Any, user_id: str, *, context: str, role: str) -> Any:
    user = user_repo.get_by_id(user_id)
    if user is None:
        raise RuntimeError(f"{context} {role} user not found: {user_id}")
    return user


def user_type(user: Any, user_id: str, *, context: str) -> str:
    raw_type = getattr(user, "type", None)
    if raw_type is None:
        raise RuntimeError(f"{context} user is missing type: {user_id}")
    return raw_type.value if isinstance(raw_type, Enum) else str(raw_type)


def display_name(user: Any, user_id: str, *, context: str) -> str:
    name = getattr(user, "display_name", None)
    if name is None:
        raise RuntimeError(f"{context} user is missing display name: {user_id}")
    return str(name)


def make_runtime_actor(
    *,
    user_id: str,
    user: Any,
    source: str,
    context: str,
    include_avatar: bool = False,
) -> AgentRuntimeActor:
    return AgentRuntimeActor(
        user_id=user_id,
        user_type=user_type(user, user_id, context=context),
        display_name=display_name(user, user_id, context=context),
        avatar_url=avatar_url(user_id, bool(getattr(user, "avatar", None))) if include_avatar else None,
        source=source,
    )
