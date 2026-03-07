"""Thread-scoped file service."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.web.core.config import DB_PATH, THREAD_FILES_ROOT


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS thread_file_channels (
            thread_id TEXT PRIMARY KEY,
            files_path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS thread_file_transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL,
            direction TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_thread_file_transfers_thread_id_created_at "
        "ON thread_file_transfers(thread_id, created_at DESC)"
    )


def _resolve_relative_path(base: Path, relative_path: str) -> Path:
    requested = Path(relative_path)
    if requested.is_absolute():
        raise ValueError(f"Path must be relative: {relative_path}")
    candidate = (base / requested).resolve()
    # @@@path-boundary - Reject traversal so API callers cannot escape per-thread files root.
    candidate.relative_to(base.resolve())
    return candidate


def _thread_files_dir(thread_id: str, workspace_id: str | None = None) -> Path:
    if workspace_id:
        # @@@lazy-import - avoid circular dep: file_channel_service ↔ workspace_service both import from config
        from backend.web.services.workspace_service import get_workspace

        ws = get_workspace(workspace_id)
        if ws is None:
            raise ValueError(f"Workspace not found: {workspace_id}")
        return Path(ws["host_path"]).resolve()
    return (THREAD_FILES_ROOT / thread_id / "files").resolve()


def ensure_thread_file_channel(thread_id: str, workspace_id: str | None = None) -> dict[str, Any]:
    # @@@workspace-root - when workspace_id set, root is shared host_path; otherwise per-thread isolation
    files_dir = _thread_files_dir(thread_id, workspace_id)
    files_dir.mkdir(parents=True, exist_ok=True)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = _now_utc()
    with sqlite3.connect(str(DB_PATH)) as conn:
        _ensure_tables(conn)
        conn.execute(
            """
            INSERT INTO thread_file_channels(thread_id, files_path, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                files_path = excluded.files_path,
                updated_at = excluded.updated_at
            """,
            (thread_id, str(files_dir), now, now),
        )
        conn.commit()
    return {
        "thread_id": thread_id,
        "workspace_id": workspace_id,
        "files_path": str(files_dir),
    }


def _get_files_dir(thread_id: str) -> Path:
    # @@@files-must-be-initialized - look up saved files_path from DB instead of reconstructing from env
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        _ensure_tables(conn)
        row = conn.execute(
            "SELECT files_path FROM thread_file_channels WHERE thread_id = ?", (thread_id,)
        ).fetchone()
    if row is None:
        raise ValueError(f"File channel not initialized for thread {thread_id}; call ensure_thread_file_channel first")
    d = Path(row[0]).resolve()
    if not d.is_dir():
        raise ValueError(f"File directory missing for thread {thread_id}")
    return d


def cleanup_thread_file_channel(thread_id: str) -> None:
    """Delete SQLite records and disk files for a thread's file channel."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        _ensure_tables(conn)
        conn.execute("DELETE FROM thread_file_channels WHERE thread_id = ?", (thread_id,))
        conn.execute("DELETE FROM thread_file_transfers WHERE thread_id = ?", (thread_id,))
        conn.commit()
    thread_root = (THREAD_FILES_ROOT / thread_id).resolve()
    if thread_root.exists():
        shutil.rmtree(thread_root)


def _record_transfer(
    *,
    thread_id: str,
    direction: str,
    relative_path: str,
    size_bytes: int,
    status: str,
) -> None:
    now = _now_utc()
    with sqlite3.connect(str(DB_PATH)) as conn:
        _ensure_tables(conn)
        conn.execute(
            """
            INSERT INTO thread_file_transfers(thread_id, direction, relative_path, size_bytes, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (thread_id, direction, relative_path, int(size_bytes), status, now),
        )
        conn.commit()


def save_uploaded_file(
    *,
    thread_id: str,
    relative_path: str,
    content: bytes,
) -> dict[str, Any]:
    base = _get_files_dir(thread_id)
    target = _resolve_relative_path(base, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    _record_transfer(
        thread_id=thread_id,
        direction="upload",
        relative_path=str(Path(relative_path)),
        size_bytes=len(content),
        status="ok",
    )
    return {
        "thread_id": thread_id,
        "relative_path": str(Path(relative_path)),
        "absolute_path": str(target),
        "size_bytes": len(content),
        "sha256": digest,
    }


def resolve_download_file(
    *,
    thread_id: str,
    relative_path: str,
) -> Path:
    base = _get_files_dir(thread_id)
    target = _resolve_relative_path(base, relative_path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"File not found: {relative_path}")

    _record_transfer(
        thread_id=thread_id,
        direction="download",
        relative_path=str(Path(relative_path)),
        size_bytes=target.stat().st_size,
        status="ok",
    )
    return target


def list_channel_files(
    *,
    thread_id: str,
) -> list[dict[str, Any]]:
    base = _get_files_dir(thread_id)
    entries: list[dict[str, Any]] = []
    for item in sorted(base.rglob("*")):
        if not item.is_file():
            continue
        entries.append(
            {
                "relative_path": str(item.relative_to(base)),
                "size_bytes": item.stat().st_size,
                "updated_at": datetime.fromtimestamp(item.stat().st_mtime, tz=UTC).isoformat(),
            }
        )
    return entries


def list_thread_file_transfers(
    *,
    thread_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_tables(conn)
        rows = conn.execute(
            """
            SELECT id, thread_id, direction, relative_path, size_bytes, status, created_at
            FROM thread_file_transfers
            WHERE thread_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (thread_id, max(1, int(limit))),
        ).fetchall()
    return [dict(row) for row in rows]
