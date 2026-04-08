"""Strategy-aware factory functions for repos used outside lifespan wiring.

Services that instantiate repos directly (task_service, cron_job_service,
monitor_service, etc.) call these helpers to get the right provider.
"""

from __future__ import annotations

import importlib
import os
from functools import lru_cache
from typing import Any


def _strategy() -> str:
    return os.getenv("LEON_STORAGE_STRATEGY", "sqlite")


def _sandbox_db_path() -> Any:
    from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path

    return resolve_role_db_path(SQLiteDBRole.SANDBOX)


@lru_cache(maxsize=1)
def _supabase_client() -> Any:
    factory_ref = os.getenv("LEON_SUPABASE_CLIENT_FACTORY", "").strip()
    if factory_ref:
        module_name, sep, attr_name = factory_ref.partition(":")
        if not sep or not module_name or not attr_name:
            raise RuntimeError("Invalid LEON_SUPABASE_CLIENT_FACTORY format. Expected '<module>:<callable>'.")
        module = importlib.import_module(module_name)
        factory = getattr(module, attr_name)
        if not callable(factory):
            raise RuntimeError(f"Supabase client factory {factory_ref!r} must be callable.")
        return factory()
    from backend.web.core.supabase_factory import create_supabase_client

    return create_supabase_client()


def make_panel_task_repo() -> Any:
    from storage.providers.supabase.panel_task_repo import SupabasePanelTaskRepo

    return SupabasePanelTaskRepo(_supabase_client())


def make_cron_job_repo() -> Any:
    from storage.providers.supabase.cron_job_repo import SupabaseCronJobRepo

    return SupabaseCronJobRepo(_supabase_client())


def make_sandbox_monitor_repo() -> Any:
    if _strategy() == "supabase":
        from storage.providers.supabase.sandbox_monitor_repo import SupabaseSandboxMonitorRepo

        return SupabaseSandboxMonitorRepo(_supabase_client())
    from storage.providers.sqlite.sandbox_monitor_repo import SQLiteSandboxMonitorRepo

    return SQLiteSandboxMonitorRepo(db_path=_sandbox_db_path())


def make_lease_repo(db_path: Any = None) -> Any:
    if _strategy() == "supabase":
        from storage.providers.supabase.lease_repo import SupabaseLeaseRepo

        return SupabaseLeaseRepo(_supabase_client())
    from storage.providers.sqlite.lease_repo import SQLiteLeaseRepo

    return SQLiteLeaseRepo(db_path=db_path or _sandbox_db_path())


def make_terminal_repo(db_path: Any = None) -> Any:
    if _strategy() == "supabase":
        from storage.providers.supabase.terminal_repo import SupabaseTerminalRepo

        return SupabaseTerminalRepo(_supabase_client())
    from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo

    return SQLiteTerminalRepo(db_path=db_path or _sandbox_db_path())


def make_chat_session_repo(db_path: Any = None) -> Any:
    if _strategy() == "supabase":
        from storage.providers.supabase.chat_session_repo import SupabaseChatSessionRepo

        return SupabaseChatSessionRepo(_supabase_client())
    from storage.providers.sqlite.chat_session_repo import SQLiteChatSessionRepo

    return SQLiteChatSessionRepo(db_path=db_path or _sandbox_db_path())


def list_resource_snapshots(lease_ids: list[str]) -> dict[str, Any]:
    if _strategy() == "supabase":
        from storage.providers.supabase.resource_snapshot_repo import list_snapshots_by_lease_ids

        return list_snapshots_by_lease_ids(lease_ids, client=_supabase_client())
    from storage.providers.sqlite.resource_snapshot_repo import list_snapshots_by_lease_ids

    return list_snapshots_by_lease_ids(lease_ids, db_path=_sandbox_db_path())
