"""Runtime wiring helpers for storage (Supabase-only)."""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from storage.container import StorageContainer

_WEB_SUPABASE_CLIENT_FACTORY = "backend.web.core.supabase_factory:create_supabase_client"


def current_storage_strategy() -> str:
    return str(os.getenv("LEON_STORAGE_STRATEGY") or "supabase").strip().lower()


def uses_supabase_storage() -> bool:
    return current_storage_strategy() == "supabase"


def uses_supabase_runtime_defaults() -> bool:
    explicit_strategy = os.getenv("LEON_STORAGE_STRATEGY")
    if explicit_strategy is not None:
        return explicit_strategy.strip().lower() == "supabase"
    return bool(os.getenv("LEON_SUPABASE_CLIENT_FACTORY"))


def build_storage_container(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    public_supabase_client: Any | None = None,
    public_supabase_client_factory: str | None = None,
    **_kwargs: Any,
) -> StorageContainer:
    """Build a runtime storage container (Supabase-only)."""
    client = _resolve_supabase_client(supabase_client, supabase_client_factory)
    public_client = (
        public_supabase_client
        if public_supabase_client is not None
        else (_resolve_supabase_client(public_supabase_client, public_supabase_client_factory) if public_supabase_client_factory else None)
    )
    return StorageContainer(supabase_client=client, public_supabase_client=public_client)


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


def build_panel_task_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **kwargs: Any,
):
    return build_storage_container(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
        public_supabase_client_factory="backend.web.core.supabase_factory:create_public_supabase_client",
        **kwargs,
    ).panel_task_repo()


def build_cron_job_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **kwargs: Any,
):
    return build_storage_container(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
        **kwargs,
    ).cron_job_repo()


def build_lease_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **kwargs: Any,
):
    return build_storage_container(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
        **kwargs,
    ).lease_repo()


def build_chat_session_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **kwargs: Any,
):
    return build_storage_container(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
        **kwargs,
    ).chat_session_repo()


def build_terminal_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **kwargs: Any,
):
    return build_storage_container(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
        **kwargs,
    ).terminal_repo()


def build_agent_registry_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **kwargs: Any,
):
    return build_storage_container(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
        public_supabase_client_factory="backend.web.core.supabase_factory:create_public_supabase_client",
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
        public_supabase_client_factory="backend.web.core.supabase_factory:create_public_supabase_client",
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


def build_sandbox_monitor_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
):
    client = _resolve_supabase_client(supabase_client, supabase_client_factory or _WEB_SUPABASE_CLIENT_FACTORY)
    from storage.providers.supabase.sandbox_monitor_repo import SupabaseSandboxMonitorRepo

    return SupabaseSandboxMonitorRepo(client)


def resolve_runtime_health_monitor_db_path(*, db_path: str | Path | None = None) -> Path | None:
    if current_storage_strategy() == "supabase":
        return None
    if db_path is not None:
        return Path(db_path)
    from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path

    return resolve_role_db_path(SQLiteDBRole.SANDBOX)


def build_runtime_health_monitor_repo(
    *,
    db_path: str | Path | None = None,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
):
    if current_storage_strategy() == "supabase":
        return build_sandbox_monitor_repo(
            supabase_client=supabase_client,
            supabase_client_factory=supabase_client_factory,
        )
    from storage.providers.sqlite.sandbox_monitor_repo import SQLiteSandboxMonitorRepo

    return SQLiteSandboxMonitorRepo(db_path=resolve_runtime_health_monitor_db_path(db_path=db_path))


def build_provider_event_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **kwargs: Any,
):
    return build_storage_container(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
        **kwargs,
    ).provider_event_repo()


def build_checkpoint_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **kwargs: Any,
):
    return build_storage_container(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
        **kwargs,
    ).checkpoint_repo()


def build_file_operation_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **kwargs: Any,
):
    return build_storage_container(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
        **kwargs,
    ).file_operation_repo()


def build_queue_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **kwargs: Any,
):
    return build_storage_container(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
        **kwargs,
    ).queue_repo()


def build_summary_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **kwargs: Any,
):
    return build_storage_container(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
        **kwargs,
    ).summary_repo()


def list_resource_snapshots(
    lease_ids: list[str],
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    repo = build_resource_snapshot_repo(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
        **kwargs,
    )
    try:
        return repo.list_snapshots_by_lease_ids(lease_ids)
    finally:
        repo.close()


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
