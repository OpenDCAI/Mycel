"""Supabase repository for sync_files state."""

from __future__ import annotations

from typing import Any

from storage.providers.supabase import _query as q

_REPO = "sync_file repo"
_TABLE = "sync_files"


class SupabaseSyncFileRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _table(self) -> Any:
        return self._client.table(_TABLE)

    def track_file(self, thread_id: str, relative_path: str, checksum: str, timestamp: int) -> None:
        self._table().upsert(
            {
                "thread_id": thread_id,
                "relative_path": relative_path,
                "checksum": checksum,
                "last_synced": timestamp,
            }
        ).execute()

    def track_files_batch(self, thread_id: str, file_records: list[tuple[str, str, int]]) -> None:
        if not file_records:
            return
        self._table().upsert(
            [{"thread_id": thread_id, "relative_path": rp, "checksum": cs, "last_synced": ts} for rp, cs, ts in file_records]
        ).execute()

    def get_file_info(self, thread_id: str, relative_path: str) -> dict | None:
        rows = q.rows(
            self._table().select("checksum,last_synced").eq("thread_id", thread_id).eq("relative_path", relative_path).execute(),
            _REPO,
            "get_file_info",
        )
        if not rows:
            return None
        return {"checksum": rows[0]["checksum"], "last_synced": rows[0]["last_synced"]}

    def get_all_files(self, thread_id: str) -> dict[str, str]:
        rows = q.rows(
            self._table().select("relative_path,checksum").eq("thread_id", thread_id).execute(),
            _REPO,
            "get_all_files",
        )
        return {r["relative_path"]: r["checksum"] for r in rows}

    def clear_thread(self, thread_id: str) -> int:
        rows = q.rows(
            self._table().delete().eq("thread_id", thread_id).execute(),
            _REPO,
            "clear_thread",
        )
        return len(rows)
