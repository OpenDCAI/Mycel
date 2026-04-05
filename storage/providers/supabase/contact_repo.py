"""Supabase-backed ContactRepo — block/mute contacts for multi-user deployment."""

from __future__ import annotations

import logging
import time
from typing import Any

from storage.contracts import ContactRow

logger = logging.getLogger(__name__)


class SupabaseContactRepo:
    """ContactRepo backed by Supabase `contacts` table.

    Schema: owner_id TEXT, target_id TEXT, relation TEXT, created_at FLOAT, updated_at FLOAT
    PK: (owner_id, target_id)
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    def close(self) -> None:
        pass

    def upsert(self, row: ContactRow) -> None:
        self._client.table("contacts").upsert(
            {
                "owner_id": row.owner_id,
                "target_id": row.target_id,
                "relation": row.relation,
                "created_at": row.created_at,
                "updated_at": row.updated_at or time.time(),
            },
            on_conflict="owner_id,target_id",
        ).execute()

    def get(self, owner_id: str, target_id: str) -> ContactRow | None:
        res = (
            self._client.table("contacts")
            .select("*")
            .eq("owner_id", owner_id)
            .eq("target_id", target_id)
            .maybe_single()
            .execute()
        )
        if not res.data:
            return None
        return self._to_row(res.data)

    def list_for_user(self, owner_id: str) -> list[ContactRow]:
        res = self._client.table("contacts").select("*").eq("owner_id", owner_id).execute()
        return [self._to_row(r) for r in (res.data or [])]

    def delete(self, owner_id: str, target_id: str) -> None:
        self._client.table("contacts").delete().eq("owner_id", owner_id).eq("target_id", target_id).execute()

    @staticmethod
    def _to_row(r: dict) -> ContactRow:
        return ContactRow(
            owner_id=r["owner_id"],
            target_id=r["target_id"],
            relation=r["relation"],
            created_at=r.get("created_at") or time.time(),
            updated_at=r.get("updated_at"),
        )
