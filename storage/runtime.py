"""Runtime wiring helpers for storage (Supabase-only)."""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from typing import Any

from storage.container import StorageContainer

_WEB_SUPABASE_CLIENT_FACTORY = "backend.web.core.supabase_factory:create_supabase_client"


def build_storage_container(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **_kwargs: Any,
) -> StorageContainer:
    """Build a runtime storage container (Supabase-only)."""
    client = _resolve_supabase_client(supabase_client, supabase_client_factory)
    return StorageContainer(supabase_client=client)


def build_thread_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **_kwargs: Any,
):
    client = _resolve_supabase_client(supabase_client, supabase_client_factory)
    from storage.providers.supabase.thread_repo import SupabaseThreadRepo

    return SupabaseThreadRepo(client)


def build_user_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **_kwargs: Any,
):
    client = _resolve_supabase_client(supabase_client, supabase_client_factory)
    from storage.providers.supabase.user_repo import SupabaseUserRepo

    return SupabaseUserRepo(client)


def build_tool_task_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **kwargs: Any,
):
    return build_storage_container(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
        **kwargs,
    ).tool_task_repo()


def build_agent_registry_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **kwargs: Any,
):
    return build_storage_container(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
        **kwargs,
    ).agent_registry_repo()


def build_sync_file_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **kwargs: Any,
):
    return build_storage_container(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
        **kwargs,
    ).sync_file_repo()


def build_resource_snapshot_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **kwargs: Any,
):
    return build_storage_container(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory or _WEB_SUPABASE_CLIENT_FACTORY,
        **kwargs,
    ).resource_snapshot_repo()


def _resolve_supabase_client(
    client: Any | None = None,
    factory_ref: str | None = None,
) -> Any:
    if client is not None:
        _ensure_supabase_client(client)
        return client
    ref = factory_ref or os.environ.get("LEON_SUPABASE_CLIENT_FACTORY")
    if not ref:
        raise RuntimeError(
            "Supabase storage requires runtime config. "
            "Set LEON_SUPABASE_CLIENT_FACTORY=<module>:<callable> "
            "or inject supabase_client explicitly."
        )
    factory = _load_factory(ref)
    result = factory()
    _ensure_supabase_client(result)
    return result


def _load_factory(factory_ref: str) -> Callable[[], Any]:
    module_name, sep, attr_name = factory_ref.partition(":")
    if not sep or not module_name or not attr_name:
        raise RuntimeError("Invalid LEON_SUPABASE_CLIENT_FACTORY format. Expected '<module>:<callable>'.")
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise RuntimeError(f"Failed to import supabase client factory module {module_name!r}: {exc}") from exc
    try:
        factory = getattr(module, attr_name)
    except AttributeError as exc:
        raise RuntimeError(f"Supabase client factory {factory_ref!r} is missing attribute {attr_name!r}.") from exc
    if not callable(factory):
        raise RuntimeError(f"Supabase client factory {factory_ref!r} must be callable.")
    return factory


def _ensure_supabase_client(client: Any) -> None:
    if client is None:
        raise RuntimeError("Supabase client factory returned None.")
    table_method = getattr(client, "table", None)
    if not callable(table_method):
        raise RuntimeError("Supabase client must expose a callable table(name) API. Check LEON_SUPABASE_CLIENT_FACTORY output.")
