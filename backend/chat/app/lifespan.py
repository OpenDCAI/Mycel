"""Minimal lifespan for the separate Chat app shell."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import is_dataclass, replace

from fastapi import FastAPI

from backend.bootstrap.app_entrypoint import resolve_app_port
from backend.bootstrap.storage import attach_runtime_storage_state
from backend.chat.bootstrap import attach_chat_runtime, wire_chat_delivery
from backend.chat.runtime_delivery import make_chat_delivery_fn
from backend.chat.transport import build_http_chat_transport
from backend.identity.auth.runtime_bootstrap import attach_auth_runtime_state
from backend.threads.runtime_read_client import build_http_thread_runtime_read_client


def _resolve_threads_backend_url() -> str:
    explicit = os.getenv("LEON_THREADS_BACKEND_URL")
    if explicit:
        return explicit.rstrip("/")
    port = resolve_app_port("LEON_THREADS_BACKEND_PORT", "worktree.ports.threads-backend", 8012)
    return f"http://127.0.0.1:{port}"


def _attach_remote_thread_reads(chat_runtime: object, thread_runtime_read_client: object) -> object:
    if is_dataclass(chat_runtime):
        return replace(
            chat_runtime,
            hire_conversation_reader=thread_runtime_read_client,
            agent_actor_lookup=thread_runtime_read_client,
        )
    setattr(chat_runtime, "hire_conversation_reader", thread_runtime_read_client)
    setattr(chat_runtime, "agent_actor_lookup", thread_runtime_read_client)
    return chat_runtime


def _require_chat_runtime_contract(app: FastAPI) -> None:
    runtime_storage = attach_runtime_storage_state(app)
    storage_container = runtime_storage.storage_container
    user_directory = storage_container.user_repo()
    attach_auth_runtime_state(
        app,
        storage_state=runtime_storage,
        contact_repo=storage_container.contact_repo(),
    )
    app.state.chat_runtime_state = attach_chat_runtime(
        app,
        storage_container,
        user_repo=user_directory,
    )
    thread_runtime_read_client = build_http_thread_runtime_read_client(base_url=_resolve_threads_backend_url())
    app.state.chat_runtime_state = _attach_remote_thread_reads(app.state.chat_runtime_state, thread_runtime_read_client)
    transport = build_http_chat_transport(base_url=_resolve_threads_backend_url())
    delivery_fn = make_chat_delivery_fn(transport=transport)
    wire_chat_delivery(
        messaging_service=app.state.chat_runtime_state.messaging_service,
        delivery_fn=delivery_fn,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _require_chat_runtime_contract(app)
    yield
