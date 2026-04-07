"""Supabase repository for chats."""

from __future__ import annotations

from typing import Any

from storage.contracts import ChatRow
from storage.providers.supabase import _query as q

_REPO_CHAT = "chat repo"
_TABLE_CHATS = "chats"


class SupabaseChatRepo:
    """Chat CRUD backed by Supabase."""

    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO_CHAT)

    def close(self) -> None:
        return None

    def create(self, row: ChatRow) -> None:
        self._t().insert(
            {
                "id": row.id,
                "title": row.title,
                "status": row.status,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        ).execute()

    def get_by_id(self, chat_id: str) -> ChatRow | None:
        response = self._t().select("*").eq("id", chat_id).execute()
        rows = q.rows(response, _REPO_CHAT, "get_by_id")
        if not rows:
            return None
        r = rows[0]
        return ChatRow(
            id=r["id"],
            title=r.get("title"),
            status=r.get("status", "active"),
            created_at=float(r["created_at"]),
            updated_at=float(r["updated_at"]) if r.get("updated_at") is not None else None,
        )

    def get_by_ids(self, chat_ids: list[str]) -> dict[str, ChatRow]:
        if not chat_ids:
            return {}
        response = self._t().select("*").in_("id", chat_ids).execute()
        rows = q.rows(response, _REPO_CHAT, "get_by_ids")
        return {
            r["id"]: ChatRow(
                id=r["id"],
                title=r.get("title"),
                status=r.get("status", "active"),
                created_at=float(r["created_at"]),
                updated_at=float(r["updated_at"]) if r.get("updated_at") is not None else None,
            )
            for r in rows
        }

    def update_title(self, chat_id: str, title: str | None) -> None:
        import time

        self._t().update({"title": title, "updated_at": time.time()}).eq("id", chat_id).execute()

    def delete(self, chat_id: str) -> None:
        self._t().delete().eq("id", chat_id).execute()

    def _t(self) -> Any:
        return self._client.table(_TABLE_CHATS)
