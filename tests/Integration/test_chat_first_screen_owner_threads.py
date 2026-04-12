from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from backend.web.routers import conversations as conversations_router
from backend.web.routers import threads as threads_router


class _CountingOwnerThreadRepo:
    def __init__(self) -> None:
        self.calls = 0
        self._lock = threading.Lock()

    def list_by_owner_user_id(self, _user_id: str) -> list[dict]:
        with self._lock:
            self.calls += 1
        time.sleep(0.05)
        return []


@pytest.mark.asyncio
async def test_first_screen_reuses_inflight_owner_thread_read_across_conversations_and_threads() -> None:
    thread_repo = _CountingOwnerThreadRepo()
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=thread_repo,
            terminal_repo=SimpleNamespace(summarize_threads=lambda _thread_ids: {}),
            agent_pool={},
            thread_last_active={},
            messaging_service=SimpleNamespace(list_conversation_summaries_for_user=lambda _user_id: []),
        )
    )

    conversations, threads = await asyncio.gather(
        conversations_router.list_conversations("owner-1", app=app),
        threads_router.list_threads("owner-1", app=app),
    )

    assert conversations == []
    assert threads == {"threads": []}
    assert thread_repo.calls == 1
