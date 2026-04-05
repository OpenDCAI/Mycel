"""Supabase repository for directional contact relationships."""

from __future__ import annotations

from typing import Any

from storage.contracts import ContactRow
from storage.providers.supabase import _query as q

_REPO = "contact repo"
_TABLE = "contacts"


class SupabaseContactRepo:
    """Directional contact relationship CRUD backed by Supabase."""

    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def upsert(self, row: ContactRow) -> None:
        self._t().upsert(
            {
                "owner_id": row.owner_id,
                "target_id": row.target_id,
                "relation": row.relation,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            },
            on_conflict="owner_id,target_id",
        ).execute()

    def get(self, owner_id: str, target_id: str) -> ContactRow | None:
        response = self._t().select("*").eq("owner_id", owner_id).eq("target_id", target_id).execute()
        rows = q.rows(response, _REPO, "get")
        if not rows:
            return None
        return self._to_row(rows[0])

    def list_for_user(self, owner_id: str) -> list[ContactRow]:
        query = q.order(
            self._t().select("*").eq("owner_id", owner_id),
            "created_at",
            desc=False,
            repo=_REPO,
            operation="list_for_user",
        )
        raw = q.rows(query.execute(), _REPO, "list_for_user")
        return [self._to_row(r) for r in raw]

    def delete(self, owner_id: str, target_id: str) -> None:
        self._t().delete().eq("owner_id", owner_id).eq("target_id", target_id).execute()

    def _to_row(self, r: dict[str, Any]) -> ContactRow:
        return ContactRow(
            owner_id=r["owner_id"],
            target_id=r["target_id"],
            relation=r["relation"],
            created_at=float(r["created_at"]),
            updated_at=float(r["updated_at"]) if r.get("updated_at") is not None else None,
        )

    def _t(self) -> Any:
        return self._client.table(_TABLE)
