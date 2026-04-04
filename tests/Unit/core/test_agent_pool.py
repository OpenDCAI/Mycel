import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.web.services import agent_pool


class _FakeThreadRepo:
    def get_by_id(self, thread_id: str):
        return {"id": thread_id, "cwd": "/tmp", "model": "leon:large"}


@pytest.mark.asyncio
async def test_get_or_create_agent_creates_once_per_thread(monkeypatch: pytest.MonkeyPatch):
    created: list[object] = []

    def _fake_create_agent_sync(
        sandbox_name: str,
        workspace_root=None,
        model_name: str | None = None,
        agent: str | None = None,
        thread_repo=None,
        entity_repo=None,
        member_repo=None,
        queue_manager=None,
        chat_repos=None,
        extra_allowed_paths=None,
        web_app=None,
    ) -> object:
        time.sleep(0.05)
        obj = SimpleNamespace()
        created.append(obj)
        return obj

    monkeypatch.setattr(agent_pool, "create_agent_sync", _fake_create_agent_sync)
    monkeypatch.setattr(agent_pool, "get_or_create_agent_id", lambda **_: "agent-1")

    app = SimpleNamespace(
        state=SimpleNamespace(
            agent_pool={},
            thread_repo=_FakeThreadRepo(),
            thread_cwd={},
            thread_sandbox={},
        )
    )

    first, second = await asyncio.gather(
        agent_pool.get_or_create_agent(app, "local", thread_id="thread-1"),
        agent_pool.get_or_create_agent(app, "local", thread_id="thread-1"),
    )

    assert len(created) == 1
    assert first is second
    assert app.state.agent_pool["thread-1:local"] is first


@pytest.mark.asyncio
async def test_get_or_create_agent_ignores_unavailable_local_cwd(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    def _fake_create_agent_sync(
        sandbox_name: str,
        workspace_root=None,
        model_name: str | None = None,
        agent: str | None = None,
        thread_repo=None,
        entity_repo=None,
        member_repo=None,
        queue_manager=None,
        chat_repos=None,
        extra_allowed_paths=None,
        web_app=None,
    ) -> object:
        captured["workspace_root"] = workspace_root
        return SimpleNamespace()

    class _ThreadRepo:
        def get_by_id(self, thread_id: str):
            return {
                "id": thread_id,
                "cwd": "/Users/lexicalmathical/Codebase/homeworks/aiagent",
                "model": "leon:large",
            }

    monkeypatch.setattr(agent_pool, "create_agent_sync", _fake_create_agent_sync)
    monkeypatch.setattr(agent_pool, "get_or_create_agent_id", lambda **_: "agent-2")
    monkeypatch.setattr(Path, "exists", lambda self: False)

    app = SimpleNamespace(
        state=SimpleNamespace(
            agent_pool={},
            thread_repo=_ThreadRepo(),
            thread_cwd={},
            thread_sandbox={},
        )
    )

    await agent_pool.get_or_create_agent(app, "local", thread_id="thread-2")

    assert captured["workspace_root"] is None
