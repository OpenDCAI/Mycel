"""Supabase repository for checkpoint/writes persistence operations."""

from __future__ import annotations

from typing import Any

from storage.providers.supabase import _query as q

_REPO = "checkpoint repo"
_TABLES = ("checkpoints", "writes", "checkpoint_writes", "checkpoint_blobs")


class SupabaseCheckpointRepo:
    """Minimal checkpoint repository backed by a Supabase client."""

    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def list_thread_ids(self) -> list[str]:
        response = self._client.table("checkpoints").select("thread_id").execute()
        rows = q.rows(response, _REPO, "list_thread_ids")
        return sorted({str(row["thread_id"]) for row in rows if row.get("thread_id")})

    def delete_thread_data(self, thread_id: str) -> None:
        for table in _TABLES:
            self._client.table(table).delete().eq("thread_id", thread_id).execute()

    def delete_checkpoints_by_ids(self, thread_id: str, checkpoint_ids: list[str]) -> None:
        if not checkpoint_ids:
            return
        for table in _TABLES:
            # @@@supabase-in-clause - keep values in explicit list for PostgREST in_.
            q.in_(
                self._client.table(table).delete().eq("thread_id", thread_id),
                "checkpoint_id", checkpoint_ids, _REPO, "delete_checkpoints_by_ids",
            ).execute()
