"""Shared owner-thread reads for bursty authenticated surfaces."""

from __future__ import annotations

import asyncio
from typing import Any

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
            task = asyncio.create_task(asyncio.to_thread(state.thread_repo.list_by_owner_user_id, user_id))
            inflight[user_id] = task

    try:
        return await task
    finally:
        if owner:
            async with lock:
                current = inflight.get(user_id)
                if current is task:
                    inflight.pop(user_id, None)
