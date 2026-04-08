from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from eval.harness.client import EvalClient


class _FakeResponse:
    def __init__(self, payload: dict | None = None) -> None:
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


@pytest.mark.asyncio
async def test_create_thread_sends_agent_user_id() -> None:
    calls: list[tuple[str, dict, dict]] = []

    async def fake_post(path: str, *, json: dict, headers: dict) -> _FakeResponse:
        calls.append((path, json, headers))
        return _FakeResponse({"thread_id": "thread-1"})

    with patch("eval.harness.client.httpx.AsyncClient", return_value=SimpleNamespace(post=fake_post)):
        client = EvalClient(base_url="http://example.test", token="tok-1")
        thread_id = await client.create_thread(agent_user_id="agent-1", sandbox="local")

    assert thread_id == "thread-1"
    assert calls == [
        (
            "/api/threads",
            {
                "agent_user_id": "agent-1",
                "sandbox": "local",
            },
            {"Authorization": "Bearer tok-1"},
        )
    ]


@pytest.mark.asyncio
async def test_run_message_uses_public_messages_path_then_thread_events_stream() -> None:
    post_calls: list[tuple[str, dict, dict]] = []
    stream_calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, *, json: dict, headers: dict) -> _FakeResponse:
        post_calls.append((path, json, headers))
        return _FakeResponse({"status": "started", "run_id": "run-1", "thread_id": "thread-1"})

    @asynccontextmanager
    async def fake_stream(method: str, path: str, *, headers: dict):
        stream_calls.append((path, headers))

        class _StreamResponse:
            def raise_for_status(self) -> None:
                return None

            async def aiter_lines(self):
                for line in (
                    "event: run_start",
                    'data: {"thread_id":"thread-1","run_id":"run-1"}',
                    "",
                    "event: text",
                    'data: {"content":"done"}',
                    "",
                    "event: run_done",
                    'data: {"thread_id":"thread-1","run_id":"run-1"}',
                    "",
                ):
                    yield line

        yield _StreamResponse()

    client_transport = SimpleNamespace(post=fake_post, stream=fake_stream)
    with patch("eval.harness.client.httpx.AsyncClient", return_value=client_transport):
        client = EvalClient(base_url="http://example.test", token="tok-1")
        capture = await client.run_message("thread-1", "hello", enable_trajectory=True)

    assert capture.text_chunks == ["done"]
    assert capture.terminal_event == "done"
    assert post_calls == [
        (
            "/api/threads/thread-1/messages",
            {
                "message": "hello",
                "enable_trajectory": True,
            },
            {"Authorization": "Bearer tok-1"},
        )
    ]
    assert stream_calls == [
        (
            "/api/threads/thread-1/events?after=0&token=tok-1",
            {"Accept": "text/event-stream"},
        )
    ]


@pytest.mark.asyncio
async def test_create_thread_falls_back_to_env_agent_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict, dict]] = []

    async def fake_post(path: str, *, json: dict, headers: dict) -> _FakeResponse:
        calls.append((path, json, headers))
        return _FakeResponse({"thread_id": "thread-1"})

    monkeypatch.setenv("LEON_EVAL_AGENT_USER_ID", "agent-from-env")
    with patch("eval.harness.client.httpx.AsyncClient", return_value=SimpleNamespace(post=fake_post)):
        client = EvalClient(base_url="http://example.test", token="tok-1")
        thread_id = await client.create_thread(sandbox="local")

    assert thread_id == "thread-1"
    assert calls[0][1]["agent_user_id"] == "agent-from-env"
