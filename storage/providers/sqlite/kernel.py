"""Unified SQLite kernel for role-based connections and consistent PRAGMA setup."""

from __future__ import annotations

import os
import sqlite3
from enum import StrEnum
from pathlib import Path
from typing import Any

WAL_MODE = "WAL"
BUSY_TIMEOUT_MS = 30_000
SYNCHRONOUS = "NORMAL"


class SQLiteDBRole(StrEnum):
    """Logical database roles used by SQLite callers."""

    MAIN = "main"
    SANDBOX = "sandbox"
    QUEUE = "queue"


def _env_path(env_var: str, default_path: Path) -> Path:
    """Return Path from environment variable if set, otherwise the default path."""
    raw = os.getenv(env_var)
    return Path(raw) if raw else default_path


def resolve_role_db_path(role: SQLiteDBRole, db_path: Path | str | None = None) -> Path:
    """Resolve role-specific DB path, honoring env overrides."""
    if db_path is not None:
        return Path(db_path)

    home_root = Path.home() / ".leon"
    main_path = _env_path("LEON_DB_PATH", home_root / "leon.db")

    if role == SQLiteDBRole.MAIN:
        return main_path
    if role == SQLiteDBRole.SANDBOX:
        return _env_path("LEON_SANDBOX_DB_PATH", home_root / "sandbox.db")
    if role == SQLiteDBRole.QUEUE:
        return _env_path("LEON_QUEUE_DB_PATH", main_path.with_name("queue.db"))
    return main_path


def apply_pragmas(conn: sqlite3.Connection) -> None:
    """Apply canonical PRAGMA settings for Leon SQLite connections."""
    conn.execute(f"PRAGMA journal_mode={WAL_MODE}")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    conn.execute(f"PRAGMA synchronous={SYNCHRONOUS}")


def connect_sqlite(
    db_path: Path | str,
    *,
    row_factory: type | None = None,
    check_same_thread: bool = True,
    timeout_ms: int = BUSY_TIMEOUT_MS,
) -> sqlite3.Connection:
    """Create a SQLite connection with unified settings."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(path),
        timeout=timeout_ms / 1000,
        check_same_thread=check_same_thread,
    )
    apply_pragmas(conn)
    if row_factory is not None:
        conn.row_factory = row_factory
    return conn


async def connect_sqlite_async(
    db_path: Path | str,
    *,
    row_factory: Any | None = None,
    timeout_ms: int = BUSY_TIMEOUT_MS,
):
    """Create async SQLite connection with unified settings."""
    import aiosqlite

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(path), timeout=timeout_ms / 1000)
    await conn.execute(f"PRAGMA journal_mode={WAL_MODE}")
    await conn.execute(f"PRAGMA busy_timeout={timeout_ms}")
    await conn.execute(f"PRAGMA synchronous={SYNCHRONOUS}")
    if row_factory is not None:
        conn.row_factory = row_factory
    return conn
