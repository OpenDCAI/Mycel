"""Runtime wiring helpers for storage (Supabase-only)."""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from typing import Any

from storage.container import StorageContainer

_WEB_SUPABASE_CLIENT_FACTORY = "backend.web.core.supabase_factory:create_supabase_client"


def uses_supabase_storage() -> bool:
    return str(os.getenv("LEON_STORAGE_STRATEGY") or "supabase").strip().lower() == "supabase"


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
) -> StorageContainer:
    """Build a runtime storage container (Supabase-only)."""
    client = _resolve_supabase_client(supabase_client, supabase_client_factory)
    if public_supabase_client is not None:
        public_client = public_supabase_client
    elif public_supabase_client_factory:
        public_client = _resolve_supabase_client(factory_ref=public_supabase_client_factory)
    else:
        public_client = None
    return StorageContainer(supabase_client=client, public_supabase_client=public_client)


def _build_storage_repo(
    repo_method: str,
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
    default_supabase_client_factory: str | None = None,
    public_supabase_client_factory: str | None = None,
) -> Any:
    container = build_storage_container(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory or default_supabase_client_factory,
        public_supabase_client_factory=public_supabase_client_factory,
    )
    return getattr(container, repo_method)()


def build_thread_repo(*, supabase_client: Any | None = None, supabase_client_factory: str | None = None):
    return _build_storage_repo("thread_repo", supabase_client=supabase_client, supabase_client_factory=supabase_client_factory)


def build_workspace_repo(*, supabase_client: Any | None = None, supabase_client_factory: str | None = None):
    return _build_storage_repo("workspace_repo", supabase_client=supabase_client, supabase_client_factory=supabase_client_factory)


def build_sandbox_repo(*, supabase_client: Any | None = None, supabase_client_factory: str | None = None):
    return _build_storage_repo("sandbox_repo", supabase_client=supabase_client, supabase_client_factory=supabase_client_factory)


def build_user_repo(*, supabase_client: Any | None = None, supabase_client_factory: str | None = None):
    return _build_storage_repo("user_repo", supabase_client=supabase_client, supabase_client_factory=supabase_client_factory)


def build_tool_task_repo(*, supabase_client: Any | None = None, supabase_client_factory: str | None = None):
    return _build_storage_repo("tool_task_repo", supabase_client=supabase_client, supabase_client_factory=supabase_client_factory)


def build_schedule_repo(*, supabase_client: Any | None = None, supabase_client_factory: str | None = None):
    return _build_storage_repo("schedule_repo", supabase_client=supabase_client, supabase_client_factory=supabase_client_factory)


def build_lease_repo(*, supabase_client: Any | None = None, supabase_client_factory: str | None = None):
    return _build_storage_repo("lease_repo", supabase_client=supabase_client, supabase_client_factory=supabase_client_factory)


def build_chat_session_repo(*, supabase_client: Any | None = None, supabase_client_factory: str | None = None):
    return _build_storage_repo("chat_session_repo", supabase_client=supabase_client, supabase_client_factory=supabase_client_factory)


def build_terminal_repo(*, supabase_client: Any | None = None, supabase_client_factory: str | None = None):
    return _build_storage_repo("terminal_repo", supabase_client=supabase_client, supabase_client_factory=supabase_client_factory)


def build_agent_registry_repo(*, supabase_client: Any | None = None, supabase_client_factory: str | None = None):
    return _build_storage_repo("agent_registry_repo", supabase_client=supabase_client, supabase_client_factory=supabase_client_factory)


def build_sync_file_repo(*, supabase_client: Any | None = None, supabase_client_factory: str | None = None):
    return _build_storage_repo(
        "sync_file_repo",
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
    )


def build_resource_snapshot_repo(*, supabase_client: Any | None = None, supabase_client_factory: str | None = None):
    return _build_storage_repo(
        "resource_snapshot_repo",
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
        default_supabase_client_factory=_WEB_SUPABASE_CLIENT_FACTORY,
    )


def build_evaluation_batch_repo(*, supabase_client: Any | None = None, supabase_client_factory: str | None = None):
    return _build_storage_repo(
        "evaluation_batch_repo",
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
        default_supabase_client_factory=_WEB_SUPABASE_CLIENT_FACTORY,
    )


def build_sandbox_monitor_repo(
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
):
    client = _resolve_supabase_client(supabase_client, supabase_client_factory or _WEB_SUPABASE_CLIENT_FACTORY)
    from storage.providers.supabase.sandbox_monitor_repo import SupabaseSandboxMonitorRepo

    return SupabaseSandboxMonitorRepo(client)


def build_provider_event_repo(*, supabase_client: Any | None = None, supabase_client_factory: str | None = None):
    return _build_storage_repo("provider_event_repo", supabase_client=supabase_client, supabase_client_factory=supabase_client_factory)


def build_checkpoint_repo(*, supabase_client: Any | None = None, supabase_client_factory: str | None = None):
    return _build_storage_repo("checkpoint_repo", supabase_client=supabase_client, supabase_client_factory=supabase_client_factory)


def build_file_operation_repo(*, supabase_client: Any | None = None, supabase_client_factory: str | None = None):
    return _build_storage_repo("file_operation_repo", supabase_client=supabase_client, supabase_client_factory=supabase_client_factory)


def build_queue_repo(*, supabase_client: Any | None = None, supabase_client_factory: str | None = None):
    return _build_storage_repo("queue_repo", supabase_client=supabase_client, supabase_client_factory=supabase_client_factory)


def build_summary_repo(*, supabase_client: Any | None = None, supabase_client_factory: str | None = None):
    return _build_storage_repo("summary_repo", supabase_client=supabase_client, supabase_client_factory=supabase_client_factory)


def list_resource_snapshots_by_sandbox(
    sessions: list[dict[str, Any]],
    *,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
) -> dict[str, dict[str, Any]]:
    repo = build_resource_snapshot_repo(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
    )
    try:
        if hasattr(repo, "list_snapshots_by_sandbox_ids"):
            return repo.list_snapshots_by_sandbox_ids(sessions)

        lease_ids: list[str] = []
        sandbox_by_lease: dict[str, str] = {}
        for session in sessions:
            sandbox_id = str(session.get("sandbox_id") or "").strip()
            lease_id = str(session.get("lease_id") or "").strip()
            if not sandbox_id or not lease_id or lease_id in sandbox_by_lease:
                continue
            sandbox_by_lease[lease_id] = sandbox_id
            lease_ids.append(lease_id)

        snapshot_by_lease = repo.list_snapshots_by_lease_ids(lease_ids)
        snapshot_by_sandbox: dict[str, dict[str, Any]] = {}
        for lease_id, snapshot in snapshot_by_lease.items():
            sandbox_id = sandbox_by_lease.get(lease_id)
            if sandbox_id:
                snapshot_by_sandbox[sandbox_id] = snapshot
        return snapshot_by_sandbox
    finally:
        repo.close()


def upsert_resource_snapshot_for_sandbox(
    *,
    sandbox_id: str,
    legacy_lease_id: str,
    provider_name: str,
    observed_state: str,
    probe_mode: str,
    cpu_used: float | None = None,
    cpu_limit: float | None = None,
    memory_used_mb: float | None = None,
    memory_total_mb: float | None = None,
    disk_used_gb: float | None = None,
    disk_total_gb: float | None = None,
    network_rx_kbps: float | None = None,
    network_tx_kbps: float | None = None,
    probe_error: str | None = None,
    supabase_client: Any | None = None,
    supabase_client_factory: str | None = None,
) -> None:
    if not sandbox_id:
        raise RuntimeError("Resource snapshot write requires sandbox_id.")
    if not legacy_lease_id:
        raise RuntimeError("Resource snapshot write requires legacy_lease_id bridge.")

    repo = build_resource_snapshot_repo(
        supabase_client=supabase_client,
        supabase_client_factory=supabase_client_factory,
    )
    try:
        if hasattr(repo, "upsert_resource_snapshot_for_sandbox"):
            repo.upsert_resource_snapshot_for_sandbox(
                sandbox_id=sandbox_id,
                legacy_lease_id=legacy_lease_id,
                provider_name=provider_name,
                observed_state=observed_state,
                probe_mode=probe_mode,
                cpu_used=cpu_used,
                cpu_limit=cpu_limit,
                memory_used_mb=memory_used_mb,
                memory_total_mb=memory_total_mb,
                disk_used_gb=disk_used_gb,
                disk_total_gb=disk_total_gb,
                network_rx_kbps=network_rx_kbps,
                network_tx_kbps=network_tx_kbps,
                probe_error=probe_error,
            )
        else:
            repo.upsert_lease_resource_snapshot(
                lease_id=legacy_lease_id,
                provider_name=provider_name,
                observed_state=observed_state,
                probe_mode=probe_mode,
                cpu_used=cpu_used,
                cpu_limit=cpu_limit,
                memory_used_mb=memory_used_mb,
                memory_total_mb=memory_total_mb,
                disk_used_gb=disk_used_gb,
                disk_total_gb=disk_total_gb,
                network_rx_kbps=network_rx_kbps,
                network_tx_kbps=network_tx_kbps,
                probe_error=probe_error,
            )
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
