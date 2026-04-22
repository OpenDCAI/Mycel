"""Shared storage bootstrap helpers for backend app entrypoints."""

from __future__ import annotations

from dataclasses import dataclass

from backend.identity.auth.supabase_runtime import create_supabase_client
from storage.runtime import build_storage_container


@dataclass(frozen=True)
class RuntimeStorageState:
    supabase_client: object
    storage_container: object
    recipe_repo: object


def build_runtime_storage_state() -> RuntimeStorageState:
    supabase_client = create_supabase_client()
    storage_container = build_storage_container(supabase_client=supabase_client)
    recipe_repo = storage_container.recipe_repo()
    return RuntimeStorageState(
        supabase_client=supabase_client,
        storage_container=storage_container,
        recipe_repo=recipe_repo,
    )


def attach_runtime_storage_state(app) -> RuntimeStorageState:
    state = build_runtime_storage_state()
    app.state.runtime_storage_state = state
    return state
