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
                "type": row.type,
                "created_by_user_id": row.created_by_user_id,
                "title": row.title,
                "status": row.status,
                "next_message_seq": row.next_message_seq,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        ).execute()

    def get_by_id(self, chat_id: str) -> ChatRow | None:
        response = self._t().select("*").eq("id", chat_id).execute()
        rows = q.rows(response, _REPO_CHAT, "get_by_id")
        if not rows:
            return None
        return _row_to_chat(rows[0])

    def list_by_ids(self, chat_ids: list[str]) -> list[ChatRow]:
        if not chat_ids:
            return []
        rows = q.rows_in_chunks(lambda: self._t().select("*"), "id", chat_ids, _REPO_CHAT, "list_by_ids")
        by_id = {row["id"]: _row_to_chat(row) for row in rows}
        return [by_id[chat_id] for chat_id in chat_ids if chat_id in by_id]

    def delete(self, chat_id: str) -> None:
        self._client.table("messages").delete().eq("chat_id", chat_id).execute()
        self._client.table("chat_members").delete().eq("chat_id", chat_id).execute()
        self._t().delete().eq("id", chat_id).execute()

    def _t(self) -> Any:
        return self._client.table(_TABLE_CHATS)


def _row_to_chat(r: dict[str, Any]) -> ChatRow:
    return ChatRow(
        id=r["id"],
        type=r["type"],
        created_by_user_id=r["created_by_user_id"],
        title=r.get("title"),
        status=r.get("status", "active"),
        next_message_seq=int(r.get("next_message_seq", 0)),
        created_at=float(r["created_at"]),
        updated_at=float(r["updated_at"]) if r.get("updated_at") is not None else None,
    )
