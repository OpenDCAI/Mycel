from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.chat.app import lifespan as chat_app_lifespan


@pytest.mark.asyncio
async def test_chat_app_lifespan_attaches_storage_auth_and_chat_runtime(monkeypatch: pytest.MonkeyPatch):
    seen: list[tuple[str, object]] = []
    contact_repo = object()
    user_repo = object()
    transport = object()
    delivery_fn = object()
    thread_runtime_read_client = object()
    runtime_storage = SimpleNamespace(
        storage_container=SimpleNamespace(
            user_repo=lambda: user_repo,
            chat_repo=lambda: object(),
            contact_repo=lambda: contact_repo,
            chat_member_repo=lambda: object(),
            messages_repo=lambda: object(),
            relationship_repo=lambda: object(),
        ),
        supabase_client=object(),
    )
    attached_chat_runtime = SimpleNamespace(messaging_service=object(), contact_repo=contact_repo)

    monkeypatch.setattr(chat_app_lifespan, "attach_runtime_storage_state", lambda _app: runtime_storage)
    monkeypatch.setattr(chat_app_lifespan, "_resolve_threads_backend_url", lambda: "http://threads-backend")
    monkeypatch.setattr(
        chat_app_lifespan,
        "build_http_thread_runtime_read_client",
        lambda *, base_url: seen.append(("thread_reads", base_url)) or thread_runtime_read_client,
    )
    monkeypatch.setattr(
        chat_app_lifespan,
        "attach_auth_runtime_state",
        lambda _app, *, storage_state, contact_repo: seen.append(("auth", contact_repo)) or object(),
    )
    monkeypatch.setattr(
        chat_app_lifespan,
        "attach_chat_runtime",
        lambda app, storage_container, *, user_repo: (
            seen.append(("chat", user_repo)),
            attached_chat_runtime,
        )[-1],
    )
    monkeypatch.setattr(
        chat_app_lifespan,
        "build_http_chat_transport",
        lambda *, base_url: seen.append(("transport", base_url)) or transport,
    )
    monkeypatch.setattr(
        chat_app_lifespan,
        "make_chat_delivery_fn",
        lambda *, transport: seen.append(("delivery_fn", transport)) or delivery_fn,
    )
    monkeypatch.setattr(
        chat_app_lifespan,
        "wire_chat_delivery",
        lambda *, messaging_service, delivery_fn: seen.append(("wire", messaging_service, delivery_fn)),
    )

    app = SimpleNamespace(state=SimpleNamespace())

    async with chat_app_lifespan.lifespan(app):
        assert app.state.chat_runtime_state is attached_chat_runtime
        assert app.state.chat_runtime_state.hire_conversation_reader is thread_runtime_read_client
        assert app.state.chat_runtime_state.agent_actor_lookup is thread_runtime_read_client

    assert seen == [
        ("auth", contact_repo),
        ("chat", user_repo),
        ("thread_reads", "http://threads-backend"),
        ("transport", "http://threads-backend"),
        ("delivery_fn", transport),
        ("wire", attached_chat_runtime.messaging_service, delivery_fn),
    ]


@pytest.mark.asyncio
async def test_chat_app_lifespan_requires_storage_runtime_contract(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        chat_app_lifespan,
        "attach_runtime_storage_state",
        lambda _app: (_ for _ in ()).throw(RuntimeError("Supabase storage requires runtime config.")),
    )

    app = SimpleNamespace(state=SimpleNamespace())

    with pytest.raises(RuntimeError, match="Supabase storage requires runtime config."):
        async with chat_app_lifespan.lifespan(app):
            raise AssertionError("lifespan should fail before yielding")


def test_resolve_threads_backend_url_prefers_explicit_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEON_THREADS_BACKEND_URL", "http://threads.example:8123/")

    assert chat_app_lifespan._resolve_threads_backend_url() == "http://threads.example:8123"


def test_resolve_threads_backend_url_falls_back_to_threads_port(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LEON_THREADS_BACKEND_URL", raising=False)
    monkeypatch.setattr(chat_app_lifespan, "resolve_app_port", lambda *_args: 55419)

    assert chat_app_lifespan._resolve_threads_backend_url() == "http://127.0.0.1:55419"
