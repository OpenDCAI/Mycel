from __future__ import annotations

import os
from pathlib import Path

from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path
from storage.runtime import build_chat_session_repo, build_lease_repo, build_terminal_repo


def resolve_sandbox_db_path(db_path: Path | None = None) -> Path:
    return db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)


def _use_strategy_control_plane_repo(db_path: Path | None = None) -> bool:
    return os.environ.get("LEON_STORAGE_STRATEGY", "sqlite").strip().lower() == "supabase" and resolve_sandbox_db_path(
        db_path
    ) == resolve_role_db_path(SQLiteDBRole.SANDBOX)


def make_chat_session_repo(db_path: Path | None = None):
    if _use_strategy_control_plane_repo(db_path):
        return build_chat_session_repo()
    from storage.providers.sqlite.chat_session_repo import SQLiteChatSessionRepo

    return SQLiteChatSessionRepo(db_path=resolve_sandbox_db_path(db_path))


def make_lease_repo(db_path: Path | None = None):
    if _use_strategy_control_plane_repo(db_path):
        return build_lease_repo()
    from storage.providers.sqlite.lease_repo import SQLiteLeaseRepo

    return SQLiteLeaseRepo(db_path=resolve_sandbox_db_path(db_path))


def make_terminal_repo(db_path: Path | None = None):
    if _use_strategy_control_plane_repo(db_path):
        return build_terminal_repo()
    from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo

    return SQLiteTerminalRepo(db_path=resolve_sandbox_db_path(db_path))
