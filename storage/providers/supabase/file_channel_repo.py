"""Supabase stub for file channel repository."""

from __future__ import annotations

from typing import Any


class SupabaseFileChannelRepo:

    def __init__(self, client: Any) -> None:
        raise NotImplementedError("SupabaseFileChannelRepo is not yet implemented")

    def close(self) -> None:
        raise NotImplementedError

    def upsert_channel(self, thread_id: str, files_path: str, now: str) -> None:
        raise NotImplementedError

    def get_files_path(self, thread_id: str) -> str | None:
        raise NotImplementedError

    def delete_channel(self, thread_id: str) -> None:
        raise NotImplementedError

    def record_transfer(self, thread_id: str, direction: str, relative_path: str, size_bytes: int, status: str, created_at: str) -> None:
        raise NotImplementedError

    def list_transfers(self, thread_id: str, limit: int = 100) -> list[dict[str, Any]]:
        raise NotImplementedError

    def delete_transfers(self, thread_id: str) -> None:
        raise NotImplementedError
