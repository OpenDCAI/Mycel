from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from backend.chat.api.http import conversations_router as owner_conversations_router
from backend.threads.owner_reads import list_owner_thread_rows_for_auth_burst
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
    async def _list_hire_conversations_for_user(_user_id: str):
        rows = await list_owner_thread_rows_for_auth_burst(app, _user_id)
        return [
            {
                "id": row["id"],
                "title": row["agent_name"],
                "avatar_url": None,
                "updated_at": None,
                "running": False,
            }
            for row in rows
        ]
    messaging_service = SimpleNamespace(list_conversation_summaries_for_user=lambda _user_id: [])
    app = SimpleNamespace(
        state=SimpleNamespace(
            terminal_repo=SimpleNamespace(summarize_threads=lambda _thread_ids: {}),
            threads_runtime_state=SimpleNamespace(
                thread_repo=thread_repo,
            ),
            chat_runtime_state=SimpleNamespace(
                hire_conversation_reader=SimpleNamespace(list_hire_conversations_for_user=_list_hire_conversations_for_user),
                messaging_service=messaging_service,
            ),
        )
    )

    conversations, threads = await asyncio.gather(
        owner_conversations_router.list_conversations(
            "owner-1",
            hire_conversation_reader=owner_conversations_router.get_hire_conversation_reader(app),
            messaging_service=app.state.chat_runtime_state.messaging_service,
        ),
        threads_router.list_threads("owner-1", app=app),
    )

    assert conversations == []
    assert threads == {"threads": []}
    assert thread_repo.calls == 1
