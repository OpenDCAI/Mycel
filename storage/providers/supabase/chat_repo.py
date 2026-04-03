"""Supabase repositories for chats, chat entities, and chat messages."""

from __future__ import annotations

import json
from typing import Any

from storage.contracts import ChatEntityRow, ChatMessageRow, ChatRow
from storage.providers.supabase import _query as q

_REPO_CHAT = "chat repo"
_TABLE_CHATS = "chats"

_REPO_ENTITY = "chat entity repo"
_TABLE_CHAT_ENTITIES = "chat_entities"

_REPO_MSG = "chat message repo"
_TABLE_CHAT_MESSAGES = "chat_messages"


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

    def delete(self, chat_id: str) -> None:
        self._t().delete().eq("id", chat_id).execute()

    def _t(self) -> Any:
        return self._client.table(_TABLE_CHATS)


class SupabaseChatEntityRepo:
    """Chat entity membership backed by Supabase."""

    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO_ENTITY)

    def close(self) -> None:
        return None

    def add_entity(self, chat_id: str, entity_id: str, joined_at: float) -> None:
        self._t().upsert(
            {
                "chat_id": chat_id,
                "entity_id": entity_id,
                "joined_at": joined_at,
            },
            on_conflict="chat_id,entity_id",
            ignore_duplicates=True,
        ).execute()

    def list_entities(self, chat_id: str) -> list[ChatEntityRow]:
        response = self._t().select("*").eq("chat_id", chat_id).execute()
        raw = q.rows(response, _REPO_ENTITY, "list_entities")
        return [self._to_entity_row(r) for r in raw]

    def list_chats_for_entity(self, entity_id: str) -> list[str]:
        response = self._t().select("chat_id").eq("entity_id", entity_id).execute()
        raw = q.rows(response, _REPO_ENTITY, "list_chats_for_entity")
        return [r["chat_id"] for r in raw]

    def is_entity_in_chat(self, chat_id: str, entity_id: str) -> bool:
        response = self._t().select("chat_id").eq("chat_id", chat_id).eq("entity_id", entity_id).execute()
        raw = q.rows(response, _REPO_ENTITY, "is_entity_in_chat")
        return len(raw) > 0

    def update_last_read(self, chat_id: str, entity_id: str, last_read_at: float) -> None:
        self._t().update({"last_read_at": last_read_at}).eq("chat_id", chat_id).eq("entity_id", entity_id).execute()

    def update_mute(self, chat_id: str, entity_id: str, muted: bool, mute_until: float | None = None) -> None:
        self._t().update({"muted": muted, "mute_until": mute_until}).eq("chat_id", chat_id).eq("entity_id", entity_id).execute()

    def find_chat_between(self, entity_a: str, entity_b: str) -> str | None:
        # Two queries, intersect the chat_id sets, then verify exactly 2 members.
        resp_a = self._t().select("chat_id").eq("entity_id", entity_a).execute()
        chats_a = {r["chat_id"] for r in q.rows(resp_a, _REPO_ENTITY, "find_chat_between(a)")}
        if not chats_a:
            return None

        resp_b = self._t().select("chat_id").eq("entity_id", entity_b).execute()
        chats_b = {r["chat_id"] for r in q.rows(resp_b, _REPO_ENTITY, "find_chat_between(b)")}

        shared = chats_a & chats_b
        if not shared:
            return None

        # Among shared chats, find one that has exactly 2 members.
        for chat_id in shared:
            resp_count = self._t().select("entity_id").eq("chat_id", chat_id).execute()
            members = q.rows(resp_count, _REPO_ENTITY, "find_chat_between(count)")
            if len(members) == 2:
                return chat_id
        return None

    def _to_entity_row(self, r: dict[str, Any]) -> ChatEntityRow:
        return ChatEntityRow(
            chat_id=r["chat_id"],
            entity_id=r["entity_id"],
            joined_at=float(r["joined_at"]),
            last_read_at=float(r["last_read_at"]) if r.get("last_read_at") is not None else None,
            muted=bool(r.get("muted", False)),
            mute_until=float(r["mute_until"]) if r.get("mute_until") is not None else None,
        )

    def _t(self) -> Any:
        return self._client.table(_TABLE_CHAT_ENTITIES)


class SupabaseChatMessageRepo:
    """Chat message persistence backed by Supabase."""

    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO_MSG)

    def close(self) -> None:
        return None

    def create(self, row: ChatMessageRow) -> None:
        mentions_json = json.dumps(row.mentioned_entity_ids) if row.mentioned_entity_ids else json.dumps([])
        self._t().insert(
            {
                "id": row.id,
                "chat_id": row.chat_id,
                "sender_entity_id": row.sender_entity_id,
                "content": row.content,
                "mentions": mentions_json,
                "created_at": row.created_at,
            }
        ).execute()

    def list_by_chat(
        self,
        chat_id: str,
        *,
        limit: int = 50,
        before: float | None = None,
    ) -> list[ChatMessageRow]:
        query = self._t().select("*").eq("chat_id", chat_id)
        if before is not None:
            query = query.lt("created_at", before)
        query = q.order(query, "created_at", desc=True, repo=_REPO_MSG, operation="list_by_chat")
        query = q.limit(query, limit, _REPO_MSG, "list_by_chat")
        raw = q.rows(query.execute(), _REPO_MSG, "list_by_chat")
        raw.reverse()
        return [self._to_msg(r) for r in raw]

    def list_unread(self, chat_id: str, entity_id: str) -> list[ChatMessageRow]:
        """Return unread messages (after last_read_at, excluding own) in chronological order."""
        # Fetch last_read_at for this entity in this chat.
        resp_ce = (
            self._client.table(_TABLE_CHAT_ENTITIES).select("last_read_at").eq("chat_id", chat_id).eq("entity_id", entity_id).execute()
        )
        ce_rows = q.rows(resp_ce, _REPO_MSG, "list_unread(last_read_at)")
        last_read: float | None = None
        if ce_rows:
            val = ce_rows[0].get("last_read_at")
            last_read = float(val) if val is not None else None

        query = self._t().select("*").eq("chat_id", chat_id).neq("sender_entity_id", entity_id)
        if last_read is not None:
            query = q.gt(query, "created_at", last_read, _REPO_MSG, "list_unread")
        query = q.order(query, "created_at", desc=False, repo=_REPO_MSG, operation="list_unread")
        raw = q.rows(query.execute(), _REPO_MSG, "list_unread")
        return [self._to_msg(r) for r in raw]

    def count_unread(self, chat_id: str, entity_id: str) -> int:
        # Fetch last_read_at for this entity in this chat.
        resp_ce = (
            self._client.table(_TABLE_CHAT_ENTITIES).select("last_read_at").eq("chat_id", chat_id).eq("entity_id", entity_id).execute()
        )
        ce_rows = q.rows(resp_ce, _REPO_MSG, "count_unread(last_read_at)")
        if not ce_rows:
            return 0
        val = ce_rows[0].get("last_read_at")
        last_read: float | None = float(val) if val is not None else None

        query = self._t().select("id", count="exact").eq("chat_id", chat_id).neq("sender_entity_id", entity_id)
        if last_read is not None:
            query = q.gt(query, "created_at", last_read, _REPO_MSG, "count_unread")
        response = query.execute()
        # supabase-py returns count on response.count when count="exact"
        count = getattr(response, "count", None)
        if count is not None:
            return int(count)
        # Fallback: count from data list.
        raw = q.rows(response, _REPO_MSG, "count_unread")
        return len(raw)

    def list_by_time_range(
        self,
        chat_id: str,
        *,
        after: float | None = None,
        before: float | None = None,
        limit: int = 100,
    ) -> list[ChatMessageRow]:
        query = self._t().select("*").eq("chat_id", chat_id)
        if after is not None:
            query = q.gte(query, "created_at", after, _REPO_MSG, "list_by_time_range")
        if before is not None:
            query = query.lte("created_at", before)
        query = q.order(query, "created_at", desc=False, repo=_REPO_MSG, operation="list_by_time_range")
        query = q.limit(query, limit, _REPO_MSG, "list_by_time_range")
        raw = q.rows(query.execute(), _REPO_MSG, "list_by_time_range")
        return [self._to_msg(r) for r in raw]

    def search(self, query: str, *, chat_id: str | None = None, limit: int = 50) -> list[ChatMessageRow]:
        base = self._t().select("*")
        if chat_id:
            base = base.eq("chat_id", chat_id)
        base = base.ilike("content", f"%{query}%")
        base = q.order(base, "created_at", desc=False, repo=_REPO_MSG, operation="search")
        base = q.limit(base, limit, _REPO_MSG, "search")
        raw = q.rows(base.execute(), _REPO_MSG, "search")
        return [self._to_msg(r) for r in raw]

    def _to_msg(self, r: dict[str, Any]) -> ChatMessageRow:
        mentions_raw = r.get("mentions")
        if mentions_raw is None or mentions_raw == "":
            mentioned: list[str] = []
        elif isinstance(mentions_raw, list):
            mentioned = mentions_raw
        else:
            try:
                loaded = json.loads(mentions_raw)
                mentioned = loaded if isinstance(loaded, list) else []
            except (json.JSONDecodeError, TypeError):
                mentioned = []
        return ChatMessageRow(
            id=r["id"],
            chat_id=r["chat_id"],
            sender_entity_id=r["sender_entity_id"],
            content=r["content"],
            mentioned_entity_ids=mentioned,
            created_at=float(r["created_at"]),
        )

    def _t(self) -> Any:
        return self._client.table(_TABLE_CHAT_MESSAGES)
