from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from backend.chat.api.http import conversations_router as owner_conversations_router
from backend.web.routers import threads as threads_router


def test_first_screen_conversations_router_owner_module_lives_under_backend_chat() -> None:
    assert owner_conversations_router.__name__ == "backend.chat.api.http.conversations_router"


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
            agent_runtime_thread_activity_reader=SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: []),
            thread_last_active={},
            messaging_service=SimpleNamespace(list_conversation_summaries_for_user=lambda _user_id: []),
        )
    )

    conversations, threads = await asyncio.gather(
        owner_conversations_router.list_conversations(
            "owner-1",
            owner_thread_rows=owner_conversations_router.get_owner_thread_rows_loader(app),
            activity_reader=app.state.agent_runtime_thread_activity_reader,
            thread_last_active=app.state.thread_last_active,
            messaging_service=app.state.messaging_service,
        ),
        threads_router.list_threads("owner-1", app=app),
    )

    assert conversations == []
    assert threads == {"threads": []}
    assert thread_repo.calls == 1
