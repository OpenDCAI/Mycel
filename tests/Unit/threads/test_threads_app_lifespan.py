from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.threads.app import lifespan as threads_app_lifespan


@pytest.mark.asyncio
async def test_threads_app_lifespan_attaches_storage_auth_and_threads_runtime(monkeypatch: pytest.MonkeyPatch):
    seen: list[tuple[str, object]] = []
    contact_repo = object()
    thread_repo = object()
    messaging_client = object()
    typing_tracker = object()
    display_builder = object()
    checkpoint_store = object()
    runtime_storage = SimpleNamespace(
        storage_container=SimpleNamespace(
            user_repo=lambda: "user-repo",
            thread_repo=lambda: thread_repo,
            queue_repo=lambda: object(),
            contact_repo=lambda: contact_repo,
            workspace_repo=lambda: "workspace-repo",
            sandbox_repo=lambda: "sandbox-repo",
            sandbox_runtime_repo=lambda: "sandbox-runtime-repo",
            lease_repo=lambda: "lease-repo",
        )
    )
    attached_threads_runtime = SimpleNamespace(agent_runtime_gateway=object())
    async def _setup():
        seen.append(("checkpoint_setup", object()))

    checkpoint_saver = SimpleNamespace(setup=_setup)

    class _CheckpointCtx:
        async def __aenter__(self):
            seen.append(("checkpoint_enter", object()))
            return checkpoint_saver

        async def __aexit__(self, *_args):
            seen.append(("checkpoint_exit", object()))
            return None

    monkeypatch.setattr(threads_app_lifespan, "attach_runtime_storage_state", lambda _app: runtime_storage)
    monkeypatch.setattr(threads_app_lifespan, "_resolve_chat_backend_url", lambda: "http://chat-backend")
    monkeypatch.setenv("LEON_POSTGRES_URL", "postgresql://example")
    monkeypatch.setattr(
        threads_app_lifespan,
        "build_http_messaging_service_client",
        lambda *, base_url: seen.append(("messaging_client", base_url)) or messaging_client,
    )
    monkeypatch.setattr(
        threads_app_lifespan,
        "build_http_typing_tracker",
        lambda *, base_url: seen.append(("typing_tracker", base_url)) or typing_tracker,
    )
    monkeypatch.setattr(threads_app_lifespan, "DisplayBuilder", lambda: display_builder)
    monkeypatch.setattr(threads_app_lifespan, "LangGraphCheckpointStore", lambda saver: checkpoint_store if saver is checkpoint_saver else None)
    monkeypatch.setattr(threads_app_lifespan, "agent_checkpoint_saver_from_conn_string", lambda url: _CheckpointCtx())
    monkeypatch.setattr(
        threads_app_lifespan,
        "attach_auth_runtime_state",
        lambda _app, *, storage_state, contact_repo: seen.append(("auth", contact_repo)) or object(),
    )
    monkeypatch.setattr(
        threads_app_lifespan,
        "attach_threads_runtime",
        lambda app, storage_container, *, thread_repo, typing_tracker, messaging_service=None: (
            seen.append(("threads", thread_repo)),
            seen.append(("typing_tracker_arg", typing_tracker)),
            seen.append(("messaging_service", messaging_service)),
            setattr(app.state, "agent_pool", {}),
            attached_threads_runtime,
        )[-1],
    )

    app = SimpleNamespace(state=SimpleNamespace())

    async with threads_app_lifespan.lifespan(app):
        assert app.state.threads_runtime_state.agent_runtime_gateway is attached_threads_runtime.agent_runtime_gateway
        assert app.state.agent_pool == {}
        assert app.state.user_repo == "user-repo"
        assert app.state.workspace_repo == "workspace-repo"
        assert app.state.sandbox_repo == "sandbox-repo"
        assert app.state.sandbox_runtime_repo == "sandbox-runtime-repo"
        assert app.state.threads_runtime_state.display_builder is display_builder
        assert app.state.threads_runtime_state.checkpoint_store is checkpoint_store
        assert app.state.threads_runtime_state.event_loop is asyncio.get_running_loop()

    assert [item[0] for item in seen] == [
        "auth",
        "messaging_client",
        "typing_tracker",
        "threads",
        "typing_tracker_arg",
        "messaging_service",
        "checkpoint_enter",
        "checkpoint_setup",
        "checkpoint_exit",
    ]


@pytest.mark.asyncio
async def test_threads_app_lifespan_requires_storage_runtime_contract(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        threads_app_lifespan,
        "attach_runtime_storage_state",
        lambda _app: (_ for _ in ()).throw(RuntimeError("Supabase storage requires runtime config.")),
    )

    app = SimpleNamespace(state=SimpleNamespace())

    with pytest.raises(RuntimeError, match="Supabase storage requires runtime config."):
        async with threads_app_lifespan.lifespan(app):
            raise AssertionError("lifespan should fail before yielding")


@pytest.mark.asyncio
async def test_threads_app_lifespan_requires_postgres_runtime_contract(monkeypatch: pytest.MonkeyPatch):
    runtime_storage = SimpleNamespace(
        storage_container=SimpleNamespace(
            user_repo=lambda: "user-repo",
            thread_repo=lambda: object(),
            queue_repo=lambda: object(),
            contact_repo=lambda: object(),
            workspace_repo=lambda: object(),
            sandbox_repo=lambda: object(),
            lease_repo=lambda: object(),
        )
    )
    monkeypatch.setattr(threads_app_lifespan, "attach_runtime_storage_state", lambda _app: runtime_storage)
    monkeypatch.delenv("LEON_POSTGRES_URL", raising=False)

    app = SimpleNamespace(state=SimpleNamespace())

    with pytest.raises(RuntimeError, match="LEON_POSTGRES_URL is required for threads backend runtime"):
        async with threads_app_lifespan.lifespan(app):
            raise AssertionError("lifespan should fail before yielding")


def test_resolve_chat_backend_url_prefers_explicit_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEON_CHAT_BACKEND_URL", "http://chat.example:8124/")

    assert threads_app_lifespan._resolve_chat_backend_url() == "http://chat.example:8124"


def test_resolve_chat_backend_url_falls_back_to_chat_port(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LEON_CHAT_BACKEND_URL", raising=False)
    monkeypatch.setattr(threads_app_lifespan, "resolve_app_port", lambda *_args: 55421)

    assert threads_app_lifespan._resolve_chat_backend_url() == "http://127.0.0.1:55421"
