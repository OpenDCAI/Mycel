from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.chat.api.http import internal_realtime_router


def test_internal_realtime_router_dispatches_typing_start_and_stop() -> None:
    seen: list[tuple[str, tuple[object, ...]]] = []

    class _TypingTracker:
        def start_chat(self, thread_id: str, chat_id: str, user_id: str) -> None:
            seen.append(("start", (thread_id, chat_id, user_id)))

        def stop(self, thread_id: str) -> None:
            seen.append(("stop", (thread_id,)))

    app = FastAPI()
    app.state.chat_runtime_state = SimpleNamespace(typing_tracker=_TypingTracker())
    app.include_router(internal_realtime_router.router)

    with TestClient(app) as client:
        start_response = client.post(
            "/api/internal/realtime/typing/start",
            json={"thread_id": "thread-1", "chat_id": "chat-1", "user_id": "agent-1"},
        )
        stop_response = client.post(
            "/api/internal/realtime/typing/stop",
            json={"thread_id": "thread-1"},
        )

    assert start_response.status_code == 200
    assert start_response.json() == {"status": "ok"}
    assert stop_response.status_code == 200
    assert stop_response.json() == {"status": "ok"}
    assert seen == [
        ("start", ("thread-1", "chat-1", "agent-1")),
        ("stop", ("thread-1",)),
    ]
