"""Supabase repository for entities."""

from __future__ import annotations

from typing import Any

from storage.contracts import EntityRow
from storage.providers.supabase import _query as q

_REPO = "entity repo"
_TABLE = "entities"


class SupabaseEntityRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def create(self, row: EntityRow) -> None:
        self._t().insert(
            {
                "id": row.id,
                "type": row.type,
                "member_id": row.member_id,
                "name": row.name,
                "avatar": row.avatar,
                "thread_id": row.thread_id,
                "created_at": row.created_at,
            }
        ).execute()

    def get_by_id(self, id: str) -> EntityRow | None:
        response = self._t().select("*").eq("id", id).execute()
        rows = q.rows(response, _REPO, "get_by_id")
        if not rows:
            return None
        return EntityRow.model_validate(rows[0])

    def get_by_member_id(self, member_id: str) -> list[EntityRow]:
        response = self._t().select("*").eq("member_id", member_id).execute()
        rows = q.rows(response, _REPO, "get_by_member_id")
        return [EntityRow.model_validate(r) for r in rows]

    def get_by_thread_id(self, thread_id: str) -> EntityRow | None:
        response = self._t().select("*").eq("thread_id", thread_id).execute()
        rows = q.rows(response, _REPO, "get_by_thread_id")
        if not rows:
            return None
        return EntityRow.model_validate(rows[0])

    def list_all(self) -> list[EntityRow]:
        query = q.order(self._t().select("*"), "created_at", desc=False, repo=_REPO, operation="list_all")
        rows = q.rows(query.execute(), _REPO, "list_all")
        return [EntityRow.model_validate(r) for r in rows]

    def list_by_type(self, entity_type: str) -> list[EntityRow]:
        query = q.order(
            self._t().select("*").eq("type", entity_type),
            "created_at",
            desc=False,
            repo=_REPO,
            operation="list_by_type",
        )
        rows = q.rows(query.execute(), _REPO, "list_by_type")
        return [EntityRow.model_validate(r) for r in rows]

    def update(self, id: str, **fields: Any) -> None:
        allowed = {"name", "avatar", "thread_id"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        self._t().update(updates).eq("id", id).execute()

    def delete(self, id: str) -> None:
        self._t().delete().eq("id", id).execute()

    def _t(self) -> Any:
        return self._client.table(_TABLE)
