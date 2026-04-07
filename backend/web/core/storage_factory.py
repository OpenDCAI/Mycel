"""Strategy-aware factory functions for repos used outside lifespan wiring.

Services that instantiate repos directly (task_service, cron_job_service,
monitor_service, etc.) call these helpers to get the right provider.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def _supabase_client() -> Any:
    from backend.web.core.supabase_factory import create_supabase_client

    return create_supabase_client()


def make_panel_task_repo() -> Any:
    from storage.providers.supabase.panel_task_repo import SupabasePanelTaskRepo

    return SupabasePanelTaskRepo(_supabase_client())


def make_cron_job_repo() -> Any:
    from storage.providers.supabase.cron_job_repo import SupabaseCronJobRepo

    return SupabaseCronJobRepo(_supabase_client())


def make_sandbox_monitor_repo() -> Any:
    from storage.providers.sqlite.sandbox_monitor_repo import SQLiteSandboxMonitorRepo

    return SQLiteSandboxMonitorRepo()


def list_resource_snapshots(lease_ids: list[str]) -> dict[str, Any]:
    from storage.providers.supabase.resource_snapshot_repo import list_snapshots_by_lease_ids

    return list_snapshots_by_lease_ids(lease_ids, client=_supabase_client())
