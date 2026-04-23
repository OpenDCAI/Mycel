"""Minimal lifespan for the separate Threads app shell."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import is_dataclass, replace
from types import SimpleNamespace

from fastapi import FastAPI

from backend.bootstrap.app_entrypoint import resolve_app_port
from backend.bootstrap.storage import attach_runtime_storage_state
from backend.chat.messaging_client import build_http_messaging_service_client
from backend.chat.typing_client import build_http_typing_tracker
from backend.identity.auth.runtime_bootstrap import attach_auth_runtime_state
from backend.threads.bootstrap import attach_threads_runtime
from backend.threads.display.builder import DisplayBuilder
from core.runtime.langgraph_checkpoint_store import LangGraphCheckpointStore, agent_checkpoint_saver_from_conn_string


def _resolve_chat_backend_url() -> str:
    explicit = os.getenv("LEON_CHAT_BACKEND_URL")
    if explicit:
        return explicit.rstrip("/")
    port = resolve_app_port("LEON_CHAT_BACKEND_PORT", "worktree.ports.chat-backend", 8013)
    return f"http://127.0.0.1:{port}"


def _require_threads_runtime_contract_env() -> str:
    pg_url = os.getenv("LEON_POSTGRES_URL")
    if not pg_url:
        raise RuntimeError("LEON_POSTGRES_URL is required for threads backend runtime")
    return pg_url


async def _attach_threads_runtime_contract(app: FastAPI) -> None:
    runtime_storage = attach_runtime_storage_state(app)
    storage_container = runtime_storage.storage_container
    pg_url = _require_threads_runtime_contract_env()
    attach_auth_runtime_state(
        app,
        storage_state=runtime_storage,
        contact_repo=storage_container.contact_repo(),
    )
    app.state.user_repo = storage_container.user_repo()
    app.state.workspace_repo = storage_container.workspace_repo()
    app.state.sandbox_repo = storage_container.sandbox_repo()
    app.state.sandbox_runtime_repo = storage_container.sandbox_runtime_repo()
    chat_backend_url = _resolve_chat_backend_url()
    messaging_service = build_http_messaging_service_client(base_url=chat_backend_url)
    typing_tracker = build_http_typing_tracker(base_url=chat_backend_url)
    app.state.threads_runtime_state = attach_threads_runtime(
        app,
        storage_container,
        thread_repo=storage_container.thread_repo(),
        typing_tracker=typing_tracker,
        messaging_service=messaging_service,
    )
    app.state._thread_checkpoint_saver_ctx = agent_checkpoint_saver_from_conn_string(pg_url)
    app.state._thread_checkpoint_saver = await app.state._thread_checkpoint_saver_ctx.__aenter__()
    await app.state._thread_checkpoint_saver.setup()
    checkpoint_store = LangGraphCheckpointStore(app.state._thread_checkpoint_saver)
    display_builder = DisplayBuilder()
    event_loop = asyncio.get_running_loop()
    runtime_state = app.state.threads_runtime_state
    if is_dataclass(runtime_state):
        runtime_state = replace(
            runtime_state,
            display_builder=display_builder,
            event_loop=event_loop,
            checkpoint_store=checkpoint_store,
        )
    else:
        runtime_state = SimpleNamespace(
            **vars(runtime_state),
            display_builder=display_builder,
            event_loop=event_loop,
            checkpoint_store=checkpoint_store,
        )
    app.state.threads_runtime_state = runtime_state


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _attach_threads_runtime_contract(app)
    try:
        yield
    finally:
        checkpoint_saver_ctx = getattr(app.state, "_thread_checkpoint_saver_ctx", None)
        if checkpoint_saver_ctx is not None:
            await checkpoint_saver_ctx.__aexit__(None, None, None)
