from __future__ import annotations

from typing import Any


def resolve_messaging_display_user(*, user_repo: Any, thread_repo: Any | None, social_user_id: str) -> Any | None:
    user = user_repo.get_by_id(social_user_id)
    if user is not None:
        return user
    if thread_repo is None:
        return None
    thread = thread_repo.get_by_user_id(social_user_id)
    if thread is None:
        return None
    agent_user_id = thread.get("agent_user_id")
    if not agent_user_id:
        return None
    return user_repo.get_by_id(agent_user_id)
