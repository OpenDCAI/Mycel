"""Shared owner-thread reads for bursty authenticated surfaces."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from backend.identity.avatar.urls import avatar_url
from backend.threads.projection import canonical_owner_threads
from backend.threads.runtime_access import get_thread_repo
from protocols.runtime_read import HireConversation, RuntimeThreadActivityReader

_LOCK_ATTR = "_owner_thread_read_lock"
_INFLIGHT_ATTR = "_owner_thread_read_inflight"


async def list_owner_thread_rows_for_auth_burst(app: Any, user_id: str) -> list[dict]:
    """Reuse only currently in-flight owner thread reads for the same user."""

    state = app.state
    lock = getattr(state, _LOCK_ATTR, None)
    if lock is None:
        lock = asyncio.Lock()
        setattr(state, _LOCK_ATTR, lock)

    async with lock:
        inflight = getattr(state, _INFLIGHT_ATTR, None)
        if inflight is None:
            inflight = {}
            setattr(state, _INFLIGHT_ATTR, inflight)

        task = inflight.get(user_id)
        owner = task is None
        if owner:
            # @@@owner-thread-read-singleflight - first-screen routes fan out together;
            # share the active repo read, then immediately forget it once complete.
            task = asyncio.create_task(asyncio.to_thread(get_thread_repo(app).list_by_owner_user_id, user_id))
            inflight[user_id] = task

    try:
        return await task
    finally:
        if owner:
            async with lock:
                current = inflight.get(user_id)
                if current is task:
                    inflight.pop(user_id, None)


class AppHireConversationReader:
    def __init__(self, app: Any, *, activity_reader: RuntimeThreadActivityReader) -> None:
        self._app = app
        self._activity_reader = activity_reader

    async def list_hire_conversations_for_user(self, user_id: str) -> list[HireConversation]:
        raw_thread_rows = await list_owner_thread_rows_for_auth_burst(self._app, user_id)
        items: list[HireConversation] = []
        raw_threads = canonical_owner_threads(raw_thread_rows)
        for thread in raw_threads:
            thread_id = str(thread["id"])
            if thread_id.startswith("subagent-"):
                continue
            last_active = self._app.state.thread_last_active.get(thread_id)
            updated_at = datetime.fromtimestamp(last_active, tz=UTC).isoformat() if last_active else None
            items.append(
                HireConversation(
                    id=thread_id,
                    title=thread.get("agent_name") or "Agent",
                    avatar_url=avatar_url(thread.get("agent_user_id"), bool(thread.get("agent_avatar"))),
                    updated_at=updated_at,
                    running=_thread_running(self._activity_reader, thread.get("agent_user_id"), thread_id),
                )
            )
        return items


def _thread_running(activity_reader: RuntimeThreadActivityReader, agent_user_id: Any, thread_id: str) -> bool:
    normalized_agent_user_id = str(agent_user_id or "").strip()
    if not normalized_agent_user_id:
        return False
    return any(
        activity.thread_id == thread_id and activity.state == "active"
        for activity in activity_reader.list_active_threads_for_agent(normalized_agent_user_id)
    )


class AppAgentActorLookup:
    def __init__(self, app: Any) -> None:
        self._app = app

    def is_agent_actor_user(self, social_user_id: str) -> bool:
        return get_thread_repo(self._app).get_canonical_thread_for_agent_actor(social_user_id) is not None
