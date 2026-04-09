from __future__ import annotations

from pathlib import Path

from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path


def resolve_sandbox_db_path(db_path: Path | None = None) -> Path:
    return db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)


def make_chat_session_repo(db_path: Path | None = None):
    from storage.providers.sqlite.chat_session_repo import SQLiteChatSessionRepo

    return SQLiteChatSessionRepo(db_path=resolve_sandbox_db_path(db_path))


def make_lease_repo(db_path: Path | None = None):
    from storage.providers.sqlite.lease_repo import SQLiteLeaseRepo

    return SQLiteLeaseRepo(db_path=resolve_sandbox_db_path(db_path))


def make_terminal_repo(db_path: Path | None = None):
    from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo

    return SQLiteTerminalRepo(db_path=resolve_sandbox_db_path(db_path))
