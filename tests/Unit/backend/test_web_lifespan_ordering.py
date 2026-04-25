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


def _patch_lifespan_runtime_contract(
    monkeypatch,
    *,
    attach_chat_runtime,
    attach_auth_runtime,
    attach_threads_runtime,
    wire_chat_delivery,
):
    monkeypatch.setattr(web_lifespan, "_require_web_runtime_contract", lambda: None)
    monkeypatch.setenv("LEON_POSTGRES_URL", "postgres://unit-test")
    monkeypatch.setenv("LEON_LOCAL_WORKSPACE_ROOT", "/tmp/mycel-unit-workspace")

    async def _no_validate():
        return None

    monkeypatch.setattr(web_lifespan, "_validate_web_checkpointer_contract", _no_validate)

    storage_container = SimpleNamespace(
        user_repo=lambda: object(),
        thread_repo=lambda: object(),
        sandbox_runtime_repo=lambda: object(),
        recipe_repo=lambda: SimpleNamespace(close=lambda: None),
        workspace_repo=lambda: object(),
        sandbox_repo=lambda: object(),
        invite_code_repo=lambda: object(),
        user_settings_repo=lambda: object(),
        agent_config_repo=lambda: object(),
        queue_repo=lambda: object(),
        contact_repo=lambda: object(),
    )

    runtime_storage = SimpleNamespace(
        supabase_client=object(),
        storage_container=storage_container,
        recipe_repo=storage_container.recipe_repo(),
    )

    monkeypatch.setattr(
        "backend.bootstrap.storage.attach_runtime_storage_state",
        lambda _app: runtime_storage,
    )
    monkeypatch.setattr(
        "backend.identity.auth.runtime_bootstrap.attach_auth_runtime_state",
        attach_auth_runtime,
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
    returned_typing_tracker = object()
    returned_messaging_service = SimpleNamespace(set_delivery_fn=lambda _fn: None)

    def _attach_chat_runtime(app, _storage_container, *, user_repo, thread_repo):
        contact_repo = object()
        return SimpleNamespace(
            contact_repo=contact_repo,
            typing_tracker=returned_typing_tracker,
            messaging_service=returned_messaging_service,
        )

    def _attach_threads_runtime(app, _storage_container, *, typing_tracker, messaging_service):
        assert typing_tracker is returned_typing_tracker
        assert messaging_service is returned_messaging_service
        app.state.agent_pool = {}
        return SimpleNamespace(activity_reader=object())

    _patch_lifespan_runtime_contract(
        monkeypatch,
        attach_chat_runtime=_attach_chat_runtime,
        attach_auth_runtime=lambda *_args, **_kwargs: object(),
        attach_threads_runtime=_attach_threads_runtime,
        wire_chat_delivery=lambda *_args, **_kwargs: None,
    )

    app = SimpleNamespace(state=SimpleNamespace())

    async with web_lifespan.lifespan(app):
        assert hasattr(app.state, "agent_pool")


@pytest.mark.asyncio
async def test_web_lifespan_wires_chat_delivery_after_threads_runtime(monkeypatch):
    call_log: list[str] = []
    returned_typing_tracker = object()
    returned_messaging_service = SimpleNamespace(set_delivery_fn=lambda _fn: None)
    returned_contact_repo = object()
    returned_activity_reader = object()

    def _attach_chat_runtime(app, _storage_container, *, user_repo, thread_repo):
        call_log.append("chat")
        return SimpleNamespace(
            contact_repo=returned_contact_repo,
            typing_tracker=returned_typing_tracker,
            messaging_service=returned_messaging_service,
        )

    def _attach_auth_runtime(_app, *, storage_state, contact_repo):
        call_log.append("auth")
        assert contact_repo is returned_contact_repo
        return object()

    def _attach_threads_runtime(app, _storage_container, *, typing_tracker, messaging_service):
        call_log.append("threads")
        assert typing_tracker is returned_typing_tracker
        assert messaging_service is returned_messaging_service
        app.state.agent_pool = {}
        return SimpleNamespace(activity_reader=returned_activity_reader)

    def _wire_chat_delivery(_app, *, messaging_service, activity_reader, thread_repo):
        call_log.append("wire")
        assert messaging_service is returned_messaging_service
        assert activity_reader is returned_activity_reader

    _patch_lifespan_runtime_contract(
        monkeypatch,
        attach_chat_runtime=_attach_chat_runtime,
        attach_auth_runtime=_attach_auth_runtime,
        attach_threads_runtime=_attach_threads_runtime,
        wire_chat_delivery=_wire_chat_delivery,
    )

    app = SimpleNamespace(state=SimpleNamespace())

    async with web_lifespan.lifespan(app):
        assert call_log == ["chat", "auth", "threads", "wire"]


@pytest.mark.asyncio
async def test_web_lifespan_passes_borrowed_contact_repo_into_auth_runtime(monkeypatch):
    seen: list[object] = []
    contact_repo = object()

    monkeypatch.setattr(web_lifespan, "_require_web_runtime_contract", lambda: None)
    monkeypatch.setenv("LEON_POSTGRES_URL", "postgres://unit-test")
    monkeypatch.setenv("LEON_LOCAL_WORKSPACE_ROOT", "/tmp/mycel-unit-workspace")

    async def _no_validate():
        return None

    monkeypatch.setattr(web_lifespan, "_validate_web_checkpointer_contract", _no_validate)

    storage_container = SimpleNamespace(
        user_repo=lambda: object(),
        thread_repo=lambda: object(),
        sandbox_runtime_repo=lambda: object(),
        recipe_repo=lambda: SimpleNamespace(close=lambda: None),
        workspace_repo=lambda: object(),
        sandbox_repo=lambda: object(),
        invite_code_repo=lambda: object(),
        user_settings_repo=lambda: object(),
        agent_config_repo=lambda: object(),
        queue_repo=lambda: object(),
        contact_repo=lambda: contact_repo,
    )

    runtime_storage = SimpleNamespace(
        supabase_client=object(),
        storage_container=storage_container,
        recipe_repo=storage_container.recipe_repo(),
    )

    monkeypatch.setattr("backend.bootstrap.storage.attach_runtime_storage_state", lambda _app: runtime_storage)
    monkeypatch.setattr(
        "backend.identity.auth.runtime_bootstrap.attach_auth_runtime_state",
        lambda _app, *, storage_state, contact_repo: seen.append(contact_repo) or object(),
    )
    monkeypatch.setattr(
        "core.runtime.langgraph_checkpoint_store.agent_checkpoint_saver_from_conn_string",
        lambda _pg_url: _FakeCheckpointCtx(),
    )
    monkeypatch.setattr(
        "core.runtime.langgraph_checkpoint_store.LangGraphCheckpointStore",
        lambda saver: SimpleNamespace(saver=saver),
    )
    monkeypatch.setattr(
        "backend.chat.bootstrap.attach_chat_runtime",
        lambda app, _storage_container, *, user_repo, thread_repo: SimpleNamespace(
            contact_repo=contact_repo,
            typing_tracker=object(),
            messaging_service=SimpleNamespace(set_delivery_fn=lambda _fn: None),
        ),
    )
    monkeypatch.setattr(
        "backend.threads.bootstrap.attach_threads_runtime",
        lambda app, *_args, **_kwargs: setattr(app.state, "agent_pool", {}) or SimpleNamespace(activity_reader=object()),
    )
    monkeypatch.setattr("backend.chat.bootstrap.wire_chat_delivery", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("backend.threads.display.builder.DisplayBuilder", lambda: object())
    monkeypatch.setattr("backend.sandboxes.service.init_providers_and_managers", lambda: None)
    monkeypatch.setattr("backend.threads.pool.idle_reaper.idle_reaper_loop", lambda _app: _never())
    monkeypatch.setattr("backend.web.core.config.IDLE_REAPER_INTERVAL_SEC", 1)

    app = SimpleNamespace(state=SimpleNamespace())

    async with web_lifespan.lifespan(app):
        assert seen == [contact_repo]


async def _never():
    try:
        await __import__("asyncio").Future()
    except BaseException:
        raise
