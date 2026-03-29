"""Supabase stub for sandbox volume repository."""

from __future__ import annotations

from typing import Any


class SupabaseSandboxVolumeRepo:

    def __init__(self, client: Any) -> None:
        raise NotImplementedError("SupabaseSandboxVolumeRepo is not yet implemented")

    def close(self) -> None:
        raise NotImplementedError

    def create(self, volume_id: str, source_json: str, name: str | None, created_at: str) -> None:
        raise NotImplementedError

    def get(self, volume_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def update_source(self, volume_id: str, source_json: str) -> None:
        raise NotImplementedError

    def list_all(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def delete(self, volume_id: str) -> bool:
        raise NotImplementedError
