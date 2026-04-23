from __future__ import annotations

import pytest

from backend.threads import runtime_read_client


def test_http_thread_runtime_read_client_reads_agent_actor_lookup(monkeypatch):
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            captured["raised"] = True

        def json(self) -> dict[str, object]:
            return {"exists": True}

    class _Client:
        def __init__(self, *, base_url: str, timeout: float, trust_env: bool) -> None:
            captured["base_url"] = base_url
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, path: str, *, params: dict | None = None) -> _Response:
            captured["path"] = path
            captured["params"] = params
            return _Response()

    monkeypatch.setattr(runtime_read_client.httpx, "Client", _Client)

    client = runtime_read_client.HttpThreadRuntimeReadClient(base_url="http://threads-backend")

    assert client.is_agent_actor_user("agent-social-1") is True
    assert captured == {
        "base_url": "http://threads-backend",
        "timeout": 10.0,
        "trust_env": False,
        "path": "/api/internal/identity/agent-actors/agent-social-1/exists",
        "params": None,
        "raised": True,
    }


@pytest.mark.asyncio
async def test_http_thread_runtime_read_client_reads_hire_conversations(monkeypatch):
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            captured["raised"] = True

        def json(self) -> list[dict[str, object]]:
            return [
                {
                    "id": "thread-1",
                    "title": "Agent",
                    "avatar_url": None,
                    "updated_at": "2026-04-22T10:00:00+00:00",
                    "running": True,
                }
            ]

    class _Client:
        def __init__(self, *, base_url: str, timeout: float, trust_env: bool) -> None:
            captured["base_url"] = base_url
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            return None

        async def get(self, path: str, *, params: dict | None = None) -> _Response:
            captured["path"] = path
            captured["params"] = params
            return _Response()

    monkeypatch.setattr(runtime_read_client.httpx, "AsyncClient", _Client)

    client = runtime_read_client.HttpThreadRuntimeReadClient(base_url="http://threads-backend")
    conversations = await client.list_hire_conversations_for_user("owner-1")

    assert len(conversations) == 1
    assert conversations[0].id == "thread-1"
    assert conversations[0].running is True
    assert captured == {
        "base_url": "http://threads-backend",
        "timeout": 10.0,
        "trust_env": False,
        "path": "/api/internal/thread-runtime/conversations/hire",
        "params": {"user_id": "owner-1"},
        "raised": True,
    }
