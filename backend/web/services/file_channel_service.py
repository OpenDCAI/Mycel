"""Thread-scoped upload/download channel service."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.web.core.config import DB_PATH, THREAD_FILES_ROOT

_ALLOWED_CHANNELS = {"upload", "download"}


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS thread_file_channels (
            thread_id TEXT PRIMARY KEY,
            root_path TEXT NOT NULL,
            upload_path TEXT NOT NULL,
            download_path TEXT NOT NULL,
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
            channel TEXT NOT NULL,
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


def _validate_channel(channel: str) -> str:
    normalized = channel.strip().lower()
    if normalized not in _ALLOWED_CHANNELS:
        raise ValueError(f"Unsupported channel: {channel}")
    return normalized


def _resolve_relative_path(base: Path, relative_path: str) -> Path:
    requested = Path(relative_path)
    if requested.is_absolute():
        raise ValueError(f"Path must be relative: {relative_path}")
    candidate = (base / requested).resolve()
    # @@@channel-path-boundary - Reject traversal so API callers cannot escape per-thread upload/download roots.
    candidate.relative_to(base.resolve())
    return candidate


def _channel_root(thread_id: str, workspace_id: str | None = None) -> Path:
    """Resolve the root directory for a thread's file channel.

    If workspace_id is given, use the workspace's host_path (shared across threads).
    Otherwise fall back to THREAD_FILES_ROOT/{thread_id} (per-thread isolation).
    """
    if workspace_id:
        from backend.web.services.workspace_service import get_workspace

        ws = get_workspace(workspace_id)
        if ws is None:
            raise ValueError(f"Workspace not found: {workspace_id}")
        return Path(ws["host_path"]).resolve()
    return (THREAD_FILES_ROOT / thread_id).resolve()


def ensure_thread_file_channel(thread_id: str, workspace_id: str | None = None) -> dict[str, str]:
    # @@@workspace-root - when workspace_id set, root is shared host_path; otherwise per-thread isolation
    thread_root = _channel_root(thread_id, workspace_id)
    upload_dir = thread_root / "upload"
    download_dir = thread_root / "download"

    upload_dir.mkdir(parents=True, exist_ok=True)
    download_dir.mkdir(parents=True, exist_ok=True)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = _now_utc()
    with sqlite3.connect(str(DB_PATH)) as conn:
        _ensure_tables(conn)
        conn.execute(
            """
            INSERT INTO thread_file_channels(thread_id, root_path, upload_path, download_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                root_path = excluded.root_path,
                upload_path = excluded.upload_path,
                download_path = excluded.download_path,
                updated_at = excluded.updated_at
            """,
            (thread_id, str(thread_root), str(upload_dir), str(download_dir), now, now),
        )
        conn.commit()
    return {
        "thread_id": thread_id,
        "workspace_id": workspace_id,
        "root_path": str(thread_root),
        "upload_path": str(upload_dir),
        "download_path": str(download_dir),
    }


def _channel_dir(thread_id: str, channel: str) -> Path:
    channel = _validate_channel(channel)
    # @@@channel-must-be-initialized - look up saved root_path from DB instead of reconstructing from env
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        _ensure_tables(conn)
        row = conn.execute(
            "SELECT root_path FROM thread_file_channels WHERE thread_id = ?", (thread_id,)
        ).fetchone()
    if row is None:
        raise ValueError(f"File channel not initialized for thread {thread_id}; call ensure_thread_file_channel first")
    d = (Path(row[0]) / channel).resolve()
    if not d.is_dir():
        raise ValueError(f"File channel directory missing for thread {thread_id} channel {channel}")
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
    channel: str,
    relative_path: str,
    size_bytes: int,
    status: str,
) -> None:
    now = _now_utc()
    with sqlite3.connect(str(DB_PATH)) as conn:
        _ensure_tables(conn)
        conn.execute(
            """
            INSERT INTO thread_file_transfers(thread_id, direction, channel, relative_path, size_bytes, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (thread_id, direction, channel, relative_path, int(size_bytes), status, now),
        )
        conn.commit()


def save_uploaded_file(
    *,
    thread_id: str,
    channel: str,
    relative_path: str,
    content: bytes,
) -> dict[str, Any]:
    channel = _validate_channel(channel)
    base = _channel_dir(thread_id, channel)
    target = _resolve_relative_path(base, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    _record_transfer(
        thread_id=thread_id,
        direction="upload",
        channel=channel,
        relative_path=str(Path(relative_path)),
        size_bytes=len(content),
        status="ok",
    )
    return {
        "thread_id": thread_id,
        "channel": channel,
        "relative_path": str(Path(relative_path)),
        "absolute_path": str(target),
        "size_bytes": len(content),
        "sha256": digest,
    }


def resolve_download_file(
    *,
    thread_id: str,
    channel: str,
    relative_path: str,
) -> Path:
    channel = _validate_channel(channel)
    base = _channel_dir(thread_id, channel)
    target = _resolve_relative_path(base, relative_path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"File not found: {relative_path}")

    _record_transfer(
        thread_id=thread_id,
        direction="download",
        channel=channel,
        relative_path=str(Path(relative_path)),
        size_bytes=target.stat().st_size,
        status="ok",
    )
    return target


def list_channel_files(
    *,
    thread_id: str,
    channel: str,
) -> list[dict[str, Any]]:
    base = _channel_dir(thread_id, channel)
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
            SELECT id, thread_id, direction, channel, relative_path, size_bytes, status, created_at
            FROM thread_file_transfers
            WHERE thread_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (thread_id, max(1, int(limit))),
        ).fetchall()
    return [dict(row) for row in rows]
