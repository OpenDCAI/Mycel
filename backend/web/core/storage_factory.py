"""Strategy-aware factory functions for repos used outside lifespan wiring.

Services that instantiate repos directly (task_service, cron_job_service,
monitor_service, etc.) call these helpers to get the right provider.

When Supabase env vars are not configured (tests/CLI), factories return
None — callers must handle this gracefully.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


_cached_client: Any | None = None
_client_resolved = False


def _supabase_client() -> Any | None:
    global _cached_client, _client_resolved
    if _client_resolved:
        return _cached_client
    from backend.web.core.supabase_factory import create_supabase_client

    try:
        _cached_client = create_supabase_client()
    except RuntimeError:
        logger.debug("Supabase not configured — factory repos will be unavailable")
        _cached_client = None
    _client_resolved = True
    return _cached_client


def make_panel_task_repo() -> Any:
    client = _supabase_client()
    if client is None:
        raise RuntimeError("Supabase required for panel_task_repo")
    from storage.providers.supabase.panel_task_repo import SupabasePanelTaskRepo

    return SupabasePanelTaskRepo(client)


def make_cron_job_repo() -> Any:
    client = _supabase_client()
    if client is None:
        raise RuntimeError("Supabase required for cron_job_repo")
    from storage.providers.supabase.cron_job_repo import SupabaseCronJobRepo

    return SupabaseCronJobRepo(client)


def make_sandbox_monitor_repo() -> Any:
    from storage.providers.sqlite.sandbox_monitor_repo import SQLiteSandboxMonitorRepo

    return SQLiteSandboxMonitorRepo()


def make_agent_registry_repo() -> Any | None:
    client = _supabase_client()
    if client is None:
        return None
    from storage.providers.supabase.agent_registry_repo import SupabaseAgentRegistryRepo

    return SupabaseAgentRegistryRepo(client)


def make_tool_task_repo(db_path: Any = None) -> Any | None:
    client = _supabase_client()
    if client is None:
        return None
    from storage.providers.supabase.tool_task_repo import SupabaseToolTaskRepo

    return SupabaseToolTaskRepo(client)


def make_sync_file_repo() -> Any | None:
    client = _supabase_client()
    if client is None:
        return None
    from storage.providers.supabase.sync_file_repo import SupabaseSyncFileRepo

    return SupabaseSyncFileRepo(client)


def upsert_resource_snapshot(**kwargs: Any) -> None:
    client = _supabase_client()
    if client is None:
        return
    from storage.providers.supabase.resource_snapshot_repo import upsert_lease_resource_snapshot

    upsert_lease_resource_snapshot(**kwargs, client=client)


def list_resource_snapshots(lease_ids: list[str]) -> dict[str, Any]:
    client = _supabase_client()
    if client is None:
        return {}
    from storage.providers.supabase.resource_snapshot_repo import list_snapshots_by_lease_ids

    return list_snapshots_by_lease_ids(lease_ids, client=client)
