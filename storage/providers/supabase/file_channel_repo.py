"""Supabase stub for file channel repository."""

from __future__ import annotations

from typing import Any


class SupabaseFileChannelRepo:

    def __init__(self, client: Any) -> None:
        raise NotImplementedError("SupabaseFileChannelRepo is not yet implemented")

    def close(self) -> None:
        raise NotImplementedError

    def create(self, channel_id: str, source_json: str, name: str | None, created_at: str) -> None:
        raise NotImplementedError

    def get(self, channel_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def update_source(self, channel_id: str, source_json: str) -> None:
        raise NotImplementedError

    def list_all(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def delete(self, channel_id: str) -> bool:
        raise NotImplementedError
