"""Strategy-aware factory functions for repos used outside lifespan wiring.

Services that instantiate repos directly (task_service, cron_job_service,
monitor_service, etc.) call these helpers to get the right provider.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any


def _strategy() -> str:
    return os.getenv("LEON_STORAGE_STRATEGY", "sqlite")


@lru_cache(maxsize=1)
def _supabase_client() -> Any:
    from backend.web.core.supabase_factory import create_supabase_client
    return create_supabase_client()


def make_panel_task_repo() -> Any:
    if _strategy() == "supabase":
        from storage.providers.supabase.panel_task_repo import SupabasePanelTaskRepo
        return SupabasePanelTaskRepo(_supabase_client())
    from backend.web.core.config import DB_PATH
    from storage.providers.sqlite.panel_task_repo import SQLitePanelTaskRepo
    return SQLitePanelTaskRepo(db_path=DB_PATH)


def make_cron_job_repo() -> Any:
    if _strategy() == "supabase":
        from storage.providers.supabase.cron_job_repo import SupabaseCronJobRepo
        return SupabaseCronJobRepo(_supabase_client())
    from backend.web.core.config import DB_PATH
    from storage.providers.sqlite.cron_job_repo import SQLiteCronJobRepo
    return SQLiteCronJobRepo(db_path=DB_PATH)


def make_sandbox_monitor_repo() -> Any:
    if _strategy() == "supabase":
        from storage.providers.supabase.sandbox_monitor_repo import SupabaseSandboxMonitorRepo
        return SupabaseSandboxMonitorRepo(_supabase_client())
    from storage.providers.sqlite.sandbox_monitor_repo import SQLiteSandboxMonitorRepo
    return SQLiteSandboxMonitorRepo()


def make_agent_registry_repo() -> Any:
    if _strategy() == "supabase":
        from storage.providers.supabase.agent_registry_repo import SupabaseAgentRegistryRepo
        return SupabaseAgentRegistryRepo(_supabase_client())
    from storage.providers.sqlite.agent_registry_repo import SQLiteAgentRegistryRepo
    return SQLiteAgentRegistryRepo()


def make_tool_task_repo(db_path: Any = None) -> Any:
    if _strategy() == "supabase":
        from storage.providers.supabase.tool_task_repo import SupabaseToolTaskRepo
        return SupabaseToolTaskRepo(_supabase_client())
    from storage.providers.sqlite.tool_task_repo import SQLiteToolTaskRepo
    if db_path is None:
        from core.tools.task.service import DEFAULT_DB_PATH
        db_path = DEFAULT_DB_PATH
    return SQLiteToolTaskRepo(db_path=db_path)


def make_sync_file_repo() -> Any:
    if _strategy() == "supabase":
        from storage.providers.supabase.sync_file_repo import SupabaseSyncFileRepo
        return SupabaseSyncFileRepo(_supabase_client())
    from storage.providers.sqlite.sync_file_repo import SQLiteSyncFileRepo
    return SQLiteSyncFileRepo()


def upsert_resource_snapshot(**kwargs: Any) -> None:
    """Strategy-aware resource snapshot upsert."""
    if _strategy() == "supabase":
        from storage.providers.supabase.resource_snapshot_repo import upsert_lease_resource_snapshot
        upsert_lease_resource_snapshot(**kwargs, client=_supabase_client())
    else:
        from storage.providers.sqlite.resource_snapshot_repo import upsert_lease_resource_snapshot
        kwargs.pop("client", None)
        upsert_lease_resource_snapshot(**kwargs)


def list_resource_snapshots(lease_ids: list[str]) -> dict[str, Any]:
    """Strategy-aware resource snapshot list."""
    if _strategy() == "supabase":
        from storage.providers.supabase.resource_snapshot_repo import list_snapshots_by_lease_ids
        return list_snapshots_by_lease_ids(lease_ids, client=_supabase_client())
    from storage.providers.sqlite.resource_snapshot_repo import list_snapshots_by_lease_ids
    return list_snapshots_by_lease_ids(lease_ids)
