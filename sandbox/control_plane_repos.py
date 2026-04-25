from __future__ import annotations

import os
from pathlib import Path

from storage.runtime import (
    build_chat_session_repo,
    build_sandbox_runtime_repo,
    build_terminal_repo,
    uses_supabase_runtime_defaults,
)


def resolve_sandbox_db_path(db_path: Path | None = None) -> Path:
    if db_path is not None:
        return db_path
    raw_path = os.getenv("LEON_SANDBOX_DB_PATH")
    if not raw_path:
        raise RuntimeError("LEON_SANDBOX_DB_PATH is required for sqlite sandbox control-plane storage.")
    return Path(raw_path)


def configured_sandbox_db_path() -> Path | None:
    raw_path = os.getenv("LEON_SANDBOX_DB_PATH")
    return Path(raw_path) if raw_path else None


def _use_strategy_control_plane_repo(db_path: Path | None = None) -> bool:
    return db_path is None and not os.getenv("LEON_SANDBOX_DB_PATH") and uses_supabase_runtime_defaults()


def make_chat_session_repo(db_path: Path | None = None):
    if _use_strategy_control_plane_repo(db_path):
        return build_chat_session_repo()
    from storage.providers.sqlite.chat_session_repo import SQLiteChatSessionRepo

    return SQLiteChatSessionRepo(db_path=resolve_sandbox_db_path(db_path))


def make_sandbox_runtime_repo(db_path: Path | None = None):
    if _use_strategy_control_plane_repo(db_path):
        return build_sandbox_runtime_repo()
    from storage.providers.sqlite.sandbox_runtime_repo import SQLiteSandboxRuntimeRepo

    return SQLiteSandboxRuntimeRepo(db_path=resolve_sandbox_db_path(db_path))


def make_terminal_repo(db_path: Path | None = None):
    if _use_strategy_control_plane_repo(db_path):
        return build_terminal_repo()
    from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo

    return SQLiteTerminalRepo(db_path=resolve_sandbox_db_path(db_path))
