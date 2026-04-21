from types import SimpleNamespace

import pytest

from backend.web.core import lifespan as web_lifespan


class _FakeCheckpointCtx:
    async def __aenter__(self):
        async def _setup():
            return None

        return SimpleNamespace(setup=_setup)

    async def __aexit__(self, exc_type, exc, tb):
        return None


def _patch_lifespan_runtime_contract(monkeypatch, *, attach_chat_runtime, attach_threads_runtime, wire_chat_delivery):
    monkeypatch.setattr(web_lifespan, "_require_web_runtime_contract", lambda: None)
    monkeypatch.setenv("LEON_POSTGRES_URL", "postgres://unit-test")

    async def _no_validate():
        return None

    monkeypatch.setattr(web_lifespan, "_validate_web_checkpointer_contract", _no_validate)

    storage_container = SimpleNamespace(
        user_repo=lambda: object(),
        thread_repo=lambda: object(),
        lease_repo=lambda: object(),
        recipe_repo=lambda: SimpleNamespace(close=lambda: None),
        workspace_repo=lambda: object(),
        sandbox_repo=lambda: object(),
        invite_code_repo=lambda: object(),
        user_settings_repo=lambda: object(),
        agent_config_repo=lambda: object(),
        queue_repo=lambda: object(),
    )

    runtime_storage = SimpleNamespace(
        supabase_client=object(),
        storage_container=storage_container,
    )

    monkeypatch.setattr(
        "backend.bootstrap.storage.attach_runtime_storage_state",
        lambda _app: runtime_storage,
    )
    monkeypatch.setattr(
        "backend.identity.auth.runtime_bootstrap.attach_auth_runtime_state",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        "core.runtime.langgraph_checkpoint_store.agent_checkpoint_saver_from_conn_string",
        lambda _pg_url: _FakeCheckpointCtx(),
    )
    monkeypatch.setattr(
        "core.runtime.langgraph_checkpoint_store.LangGraphCheckpointStore",
        lambda saver: SimpleNamespace(saver=saver),
    )
    monkeypatch.setattr("backend.chat.bootstrap.attach_chat_runtime", attach_chat_runtime)
    monkeypatch.setattr("backend.chat.bootstrap.wire_chat_delivery", wire_chat_delivery)
    monkeypatch.setattr("backend.threads.bootstrap.attach_threads_runtime", attach_threads_runtime)
    monkeypatch.setattr("backend.threads.display.builder.DisplayBuilder", lambda: object())
    monkeypatch.setattr("backend.sandboxes.service.init_providers_and_managers", lambda: None)
    monkeypatch.setattr("backend.threads.pool.idle_reaper.idle_reaper_loop", lambda _app: _never())
    monkeypatch.setattr("backend.web.core.config.IDLE_REAPER_INTERVAL_SEC", 1)


@pytest.mark.asyncio
async def test_web_lifespan_attaches_chat_runtime_before_threads_runtime(monkeypatch):
    def _attach_chat_runtime(app, _storage_container, *, user_repo, thread_repo):
        app.state.typing_tracker = object()
        app.state.messaging_service = SimpleNamespace(set_delivery_fn=lambda _fn: None)

    def _attach_threads_runtime(app, _storage_container):
        if not hasattr(app.state, "typing_tracker"):
            raise RuntimeError("threads runtime needs typing_tracker first")
        app.state.agent_pool = {}
        app.state.agent_runtime_thread_activity_reader = object()

    _patch_lifespan_runtime_contract(
        monkeypatch,
        attach_chat_runtime=_attach_chat_runtime,
        attach_threads_runtime=_attach_threads_runtime,
        wire_chat_delivery=lambda *_args, **_kwargs: None,
    )

    app = SimpleNamespace(state=SimpleNamespace())

    async with web_lifespan.lifespan(app):
        assert hasattr(app.state, "typing_tracker")
        assert hasattr(app.state, "agent_pool")


@pytest.mark.asyncio
async def test_web_lifespan_wires_chat_delivery_after_threads_runtime(monkeypatch):
    call_log: list[str] = []

    def _attach_chat_runtime(app, _storage_container, *, user_repo, thread_repo):
        call_log.append("chat")
        app.state.typing_tracker = object()
        app.state.messaging_service = SimpleNamespace(set_delivery_fn=lambda _fn: None)

    def _attach_threads_runtime(app, _storage_container):
        call_log.append("threads")
        app.state.agent_pool = {}
        app.state.agent_runtime_thread_activity_reader = object()

    def _wire_chat_delivery(_app, *, activity_reader, thread_repo):
        call_log.append("wire")
        assert activity_reader is _app.state.agent_runtime_thread_activity_reader

    _patch_lifespan_runtime_contract(
        monkeypatch,
        attach_chat_runtime=_attach_chat_runtime,
        attach_threads_runtime=_attach_threads_runtime,
        wire_chat_delivery=_wire_chat_delivery,
    )

    app = SimpleNamespace(state=SimpleNamespace())

    async with web_lifespan.lifespan(app):
        assert call_log == ["chat", "threads", "wire"]


async def _never():
    try:
        await __import__("asyncio").Future()
    except BaseException:
        raise
