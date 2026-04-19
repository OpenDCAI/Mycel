"""Shared storage bootstrap helpers for backend app entrypoints."""

from __future__ import annotations

from dataclasses import dataclass

from backend.web.core.supabase_factory import create_supabase_client
from storage.runtime import build_storage_container


@dataclass(frozen=True)
class RuntimeStorageState:
    supabase_client: object
    storage_container: object


def build_runtime_storage_state() -> RuntimeStorageState:
    supabase_client = create_supabase_client()
    storage_container = build_storage_container(supabase_client=supabase_client)
    return RuntimeStorageState(
        supabase_client=supabase_client,
        storage_container=storage_container,
    )


def attach_runtime_storage_state(app) -> RuntimeStorageState:
    state = build_runtime_storage_state()
    app.state._supabase_client = state.supabase_client
    app.state._storage_container = state.storage_container
    return state
