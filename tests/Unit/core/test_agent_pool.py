import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

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
        bundle_dir=None,
        agent_config_id=None,
        agent_config_repo=None,
        thread_repo=None,
        user_repo=None,
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
        agent_pool.get_or_create_agent(cast(Any, app), "local", thread_id="thread-1"),
        agent_pool.get_or_create_agent(cast(Any, app), "local", thread_id="thread-1"),
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
        bundle_dir=None,
        agent_config_id=None,
        agent_config_repo=None,
        thread_repo=None,
        user_repo=None,
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

    await agent_pool.get_or_create_agent(cast(Any, app), "local", thread_id="thread-2")

    assert captured["workspace_root"] is None


@pytest.mark.asyncio
async def test_get_or_create_agent_honors_fresh_local_thread_cwd_even_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path):
    captured: dict[str, object] = {}
    requested = tmp_path / "fresh-workspace"

    def _fake_create_agent_sync(
        sandbox_name: str,
        workspace_root=None,
        model_name: str | None = None,
        agent: str | None = None,
        bundle_dir=None,
        agent_config_id=None,
        agent_config_repo=None,
        thread_repo=None,
        user_repo=None,
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
                "cwd": None,
                "model": "leon:large",
            }

    monkeypatch.setattr(agent_pool, "create_agent_sync", _fake_create_agent_sync)
    monkeypatch.setattr(agent_pool, "get_or_create_agent_id", lambda **_: "agent-3")

    app = SimpleNamespace(
        state=SimpleNamespace(
            agent_pool={},
            thread_repo=_ThreadRepo(),
            thread_cwd={"thread-3": str(requested)},
            thread_sandbox={},
        )
    )

    await agent_pool.get_or_create_agent(cast(Any, app), "local", thread_id="thread-3")

    assert captured["workspace_root"] == requested.resolve()
    assert requested.is_dir()
    assert app.state.thread_cwd["thread-3"] == str(requested.resolve())


@pytest.mark.asyncio
async def test_get_or_create_agent_passes_member_bundle_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def _fake_create_agent_sync(
        sandbox_name: str,
        workspace_root=None,
        model_name: str | None = None,
        agent: str | None = None,
        bundle_dir=None,
        agent_config_id=None,
        agent_config_repo=None,
        thread_repo=None,
        user_repo=None,
        queue_manager=None,
        chat_repos=None,
        extra_allowed_paths=None,
        web_app=None,
    ) -> object:
        captured["bundle_dir"] = bundle_dir
        captured["agent_config_id"] = agent_config_id
        captured["agent_config_repo"] = agent_config_repo
        return SimpleNamespace()

    class _ThreadRepo:
        def get_by_id(self, thread_id: str):
            return {
                "id": thread_id,
                "cwd": None,
                "model": "leon:large",
                "agent_user_id": "member-1",
            }

    monkeypatch.setattr(agent_pool, "create_agent_sync", _fake_create_agent_sync)
    monkeypatch.setattr(agent_pool, "get_or_create_agent_id", lambda **_: "agent-4")

    app = SimpleNamespace(
        state=SimpleNamespace(
            agent_pool={},
            thread_repo=_ThreadRepo(),
            user_repo=SimpleNamespace(
                get_by_id=lambda user_id: SimpleNamespace(id=user_id, agent_config_id="cfg-1", owner_user_id="owner-1")
            ),
            agent_config_repo=SimpleNamespace(),
            thread_cwd={},
            thread_sandbox={},
        )
    )

    await agent_pool.get_or_create_agent(cast(Any, app), "local", thread_id="thread-4")

    assert captured["bundle_dir"] is None
    assert captured["agent_config_id"] == "cfg-1"
    assert captured["agent_config_repo"] is app.state.agent_config_repo


@pytest.mark.asyncio
async def test_get_or_create_agent_uses_thread_user_id_for_chat_identity(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    def _fake_create_agent_sync(
        sandbox_name: str,
        workspace_root=None,
        model_name: str | None = None,
        agent: str | None = None,
        bundle_dir=None,
        agent_config_id=None,
        agent_config_repo=None,
        thread_repo=None,
        user_repo=None,
        queue_manager=None,
        chat_repos=None,
        extra_allowed_paths=None,
        web_app=None,
    ) -> object:
        captured["chat_repos"] = chat_repos
        return SimpleNamespace()

    class _ThreadRepo:
        def get_by_id(self, thread_id: str):
            return {
                "id": thread_id,
                "agent_user_id": "agent-user-5",
                "cwd": None,
                "model": "leon:large",
            }

    class _UserRepo:
        def get_by_id(self, user_id: str):
            return SimpleNamespace(id=user_id, owner_user_id="owner-5", agent_config_id="cfg-5")

    monkeypatch.setattr(agent_pool, "create_agent_sync", _fake_create_agent_sync)
    monkeypatch.setattr(agent_pool, "get_or_create_agent_id", lambda **_: "agent-5")

    app = SimpleNamespace(
        state=SimpleNamespace(
            agent_pool={},
            thread_repo=_ThreadRepo(),
            user_repo=_UserRepo(),
            agent_config_repo=SimpleNamespace(),
            thread_cwd={},
            thread_sandbox={},
        )
    )

    await agent_pool.get_or_create_agent(cast(Any, app), "local", thread_id="thread-5")

    chat_repos = cast(dict[str, object], captured["chat_repos"])
    assert chat_repos["chat_identity_id"] == "agent-user-5"
    assert chat_repos["user_id"] == "agent-user-5"
    assert chat_repos["owner_id"] == "owner-5"


@pytest.mark.asyncio
async def test_get_or_create_agent_requires_thread_agent_user_id_for_chat_identity(monkeypatch: pytest.MonkeyPatch):
    def _fake_create_agent_sync(**kwargs) -> object:
        return SimpleNamespace()

    class _ThreadRepo:
        def get_by_id(self, thread_id: str):
            return {
                "id": thread_id,
                "cwd": None,
                "model": "leon:large",
            }

    class _UserRepo:
        def get_by_id(self, user_id: str):
            return SimpleNamespace(id=user_id, owner_user_id="owner-6")

    monkeypatch.setattr(agent_pool, "create_agent_sync", _fake_create_agent_sync)
    monkeypatch.setattr(agent_pool, "get_or_create_agent_id", lambda **_: "agent-6")

    app = SimpleNamespace(
        state=SimpleNamespace(
            agent_pool={},
            thread_repo=_ThreadRepo(),
            user_repo=_UserRepo(),
            thread_cwd={},
            thread_sandbox={},
        )
    )

    with pytest.raises(RuntimeError, match="thread.agent_user_id"):
        await agent_pool.get_or_create_agent(cast(Any, app), "local", thread_id="thread-6")


@pytest.mark.asyncio
async def test_get_or_create_agent_keys_registry_by_agent_user_id(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, object] = {}

    def _fake_create_agent_sync(**kwargs) -> object:
        return SimpleNamespace()

    def _fake_get_or_create_agent_id(**kwargs) -> str:
        seen.update(kwargs)
        return "agent-7"

    class _ThreadRepo:
        def get_by_id(self, thread_id: str):
            return {
                "id": thread_id,
                "agent_user_id": "agent-user-7",
                "cwd": None,
                "model": "leon:large",
            }

    monkeypatch.setattr(agent_pool, "create_agent_sync", _fake_create_agent_sync)
    monkeypatch.setattr(agent_pool, "get_or_create_agent_id", _fake_get_or_create_agent_id)

    class _UserRepo:
        def get_by_id(self, user_id: str):
            return SimpleNamespace(id=user_id, owner_user_id="owner-7", agent_config_id="cfg-7")

    app = SimpleNamespace(
        state=SimpleNamespace(
            agent_pool={},
            thread_repo=_ThreadRepo(),
            user_repo=_UserRepo(),
            agent_config_repo=SimpleNamespace(),
            thread_cwd={},
            thread_sandbox={},
        )
    )

    await agent_pool.get_or_create_agent(cast(Any, app), "local", thread_id="thread-7")

    assert seen["user_id"] == "agent-user-7"
    assert "member" not in seen
