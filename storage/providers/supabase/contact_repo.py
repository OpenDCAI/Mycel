"""Supabase repository for directional contact relationships."""

from __future__ import annotations

from typing import Any

from storage.contracts import ContactEdgeRow
from storage.providers.supabase import _query as q

_REPO = "contact repo"
_TABLE = "contacts"


class SupabaseContactRepo:
    """Directional contact relationship CRUD backed by Supabase."""

    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def upsert(self, row: ContactEdgeRow) -> None:
        self._t().upsert(
            {
                "source_user_id": row.source_user_id,
                "target_user_id": row.target_user_id,
                "kind": row.kind,
                "state": row.state,
                "muted": int(row.muted),
                "blocked": int(row.blocked),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            },
            on_conflict="source_user_id,target_user_id",
        ).execute()

    def get(self, owner_id: str, target_id: str) -> ContactEdgeRow | None:
        response = self._t().select("*").eq("source_user_id", owner_id).eq("target_user_id", target_id).execute()
        rows = q.rows(response, _REPO, "get")
        if not rows:
            return None
        return self._to_row(rows[0])

    def list_for_user(self, owner_id: str) -> list[ContactEdgeRow]:
        query = q.order(
            self._t().select("*").eq("source_user_id", owner_id),
            "created_at",
            desc=False,
            repo=_REPO,
            operation="list_for_user",
        )
        raw = q.rows(query.execute(), _REPO, "list_for_user")
        return [self._to_row(r) for r in raw]

    def delete(self, owner_id: str, target_id: str) -> None:
        self._t().delete().eq("source_user_id", owner_id).eq("target_user_id", target_id).execute()

    def _to_row(self, r: dict[str, Any]) -> ContactEdgeRow:
        return ContactEdgeRow(
            source_user_id=r["source_user_id"],
            target_user_id=r["target_user_id"],
            kind=r["kind"],
            state=r["state"],
            muted=bool(r.get("muted")),
            blocked=bool(r.get("blocked")),
            created_at=float(r["created_at"]),
            updated_at=float(r["updated_at"]) if r.get("updated_at") is not None else None,
        )

    def _t(self) -> Any:
        return self._client.table(_TABLE)
