"""Supabase sandbox volume repository."""

from __future__ import annotations

from typing import Any

from ._query import rows, validate_client


class SupabaseSandboxVolumeRepo:
    _TABLE = "sandbox_volumes"

    def __init__(self, client: Any) -> None:
        self._client = validate_client(client, "SupabaseSandboxVolumeRepo")

    def close(self) -> None:
        pass

    def create(self, volume_id: str, source_json: str, name: str | None, created_at: str) -> None:
        self._client.table(self._TABLE).insert(
            {"volume_id": volume_id, "source": source_json, "name": name, "created_at": created_at}
        ).execute()

    def get(self, volume_id: str) -> dict[str, Any] | None:
        resp = self._client.table(self._TABLE).select("*").eq("volume_id", volume_id).execute()
        data = rows(resp, "SupabaseSandboxVolumeRepo", "get")
        return data[0] if data else None

    def update_source(self, volume_id: str, source_json: str) -> None:
        self._client.table(self._TABLE).update({"source": source_json}).eq("volume_id", volume_id).execute()

    def list_all(self) -> list[dict[str, Any]]:
        resp = self._client.table(self._TABLE).select("*").order("created_at", desc=True).execute()
        return rows(resp, "SupabaseSandboxVolumeRepo", "list_all")

    def delete(self, volume_id: str) -> bool:
        resp = self._client.table(self._TABLE).delete().eq("volume_id", volume_id).execute()
        data = rows(resp, "SupabaseSandboxVolumeRepo", "delete")
        return len(data) > 0
