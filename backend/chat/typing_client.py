"""HTTP-backed typing tracker for cross-backend chat realtime updates."""

from __future__ import annotations

import httpx


class HttpTypingTracker:
    def __init__(self, *, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self._base_url, timeout=self._timeout, trust_env=False)

    def start_chat(self, thread_id: str, chat_id: str, user_id: str) -> None:
        with self._client() as client:
            response = client.post(
                "/api/internal/realtime/typing/start",
                json={"thread_id": thread_id, "chat_id": chat_id, "user_id": user_id},
            )
            response.raise_for_status()

    def stop(self, thread_id: str) -> None:
        with self._client() as client:
            response = client.post(
                "/api/internal/realtime/typing/stop",
                json={"thread_id": thread_id},
            )
            response.raise_for_status()


def build_http_typing_tracker(*, base_url: str, timeout: float = 10.0) -> HttpTypingTracker:
    return HttpTypingTracker(base_url=base_url, timeout=timeout)
