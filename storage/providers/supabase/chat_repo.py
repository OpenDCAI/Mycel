"""Supabase repositories for chats, chat entities, and chat messages."""

from __future__ import annotations

import json
from typing import Any

from storage.contracts import ChatEntityRow, ChatMessageRow, ChatRow
from storage.providers.supabase import _query as q
from storage.providers.supabase.schema import resolve_runtime_schema, route_for_schema

_REPO_CHAT = "chat repo"
_TABLE_CHATS = "chats"

_REPO_ENTITY = "chat entity repo"
_TABLE_CHAT_ENTITIES = "chat_entities"

_REPO_MSG = "chat message repo"
_TABLE_CHAT_MESSAGES = "chat_messages"
_CHAT_MEMBER_TABLES = {
    "public": _TABLE_CHAT_ENTITIES,
    "staging": "chat_members",
}
_MESSAGE_TABLES = {
    "public": _TABLE_CHAT_MESSAGES,
    "staging": "messages",
}


class SupabaseChatRepo:
    """Chat CRUD backed by Supabase."""

    def __init__(self, client: Any, *, schema: str | None = None) -> None:
        self._client = q.validate_client(client, _REPO_CHAT)
        self._schema = resolve_runtime_schema(schema)

    def close(self) -> None:
        return None

    def create(self, row: ChatRow) -> None:
        payload = {
            "id": row.id,
            "title": row.title,
            "status": row.status,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        if self._schema == "staging":
            if not row.created_by_user_id:
                raise ValueError("created_by_user_id is required for staging.chats")
            payload["type"] = row.type
            payload["created_by_user_id"] = row.created_by_user_id
        self._t().insert(payload).execute()

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
            type=r.get("type", "direct"),
            created_by_user_id=r.get("created_by_user_id"),
        )

    def delete(self, chat_id: str) -> None:
        self._t().delete().eq("id", chat_id).execute()

    def _t(self) -> Any:
        return self._client.table(_TABLE_CHATS)


class SupabaseChatEntityRepo:
    """Chat entity membership backed by Supabase."""

    def __init__(self, client: Any, *, schema: str | None = None) -> None:
        self._client = q.validate_client(client, _REPO_ENTITY)
        self._schema = resolve_runtime_schema(schema)

    def close(self) -> None:
        return None

    def add_participant(self, chat_id: str, user_id: str, joined_at: float) -> None:
        self._t().upsert(
            {
                "chat_id": chat_id,
                "user_id": user_id,
                "joined_at": joined_at,
            },
            on_conflict="chat_id,user_id",
            ignore_duplicates=True,
        ).execute()

    def list_participants(self, chat_id: str) -> list[ChatEntityRow]:
        response = self._t().select("*").eq("chat_id", chat_id).execute()
        raw = q.rows(response, _REPO_ENTITY, "list_participants")
        return [self._to_entity_row(r) for r in raw]

    def list_chats_for_user(self, user_id: str) -> list[str]:
        response = self._t().select("chat_id").eq("user_id", user_id).execute()
        raw = q.rows(response, _REPO_ENTITY, "list_chats_for_user")
        return [r["chat_id"] for r in raw]

    def is_participant_in_chat(self, chat_id: str, user_id: str) -> bool:
        response = self._t().select("chat_id").eq("chat_id", chat_id).eq("user_id", user_id).execute()
        raw = q.rows(response, _REPO_ENTITY, "is_participant_in_chat")
        return len(raw) > 0

    def update_last_read(self, chat_id: str, user_id: str, last_read_at: float) -> None:
        if self._schema == "staging":
            # @@@seq-read-watermark - the API still says "mark read now"; staging stores the latest message seq instead of a timestamp.
            latest_seq = self._latest_message_seq(chat_id)
            self._t().update({"last_read_seq": latest_seq}).eq("chat_id", chat_id).eq("user_id", user_id).execute()
            return
        self._t().update({"last_read_at": last_read_at}).eq("chat_id", chat_id).eq("user_id", user_id).execute()

    def update_mute(self, chat_id: str, user_id: str, muted: bool, mute_until: float | None = None) -> None:
        self._t().update({"muted": muted, "mute_until": mute_until}).eq("chat_id", chat_id).eq("user_id", user_id).execute()

    def find_chat_between(self, user_a: str, user_b: str) -> str | None:
        # Two queries, intersect the chat_id sets, then verify exactly 2 members.
        resp_a = self._t().select("chat_id").eq("user_id", user_a).execute()
        chats_a = {r["chat_id"] for r in q.rows(resp_a, _REPO_ENTITY, "find_chat_between(a)")}
        if not chats_a:
            return None

        resp_b = self._t().select("chat_id").eq("user_id", user_b).execute()
        chats_b = {r["chat_id"] for r in q.rows(resp_b, _REPO_ENTITY, "find_chat_between(b)")}

        shared = chats_a & chats_b
        if not shared:
            return None

        # Among shared chats, find one that has exactly 2 members.
        for chat_id in shared:
            resp_count = self._t().select("user_id").eq("chat_id", chat_id).execute()
            members = q.rows(resp_count, _REPO_ENTITY, "find_chat_between(count)")
            if len(members) == 2:
                return chat_id
        return None

    def _to_entity_row(self, r: dict[str, Any]) -> ChatEntityRow:
        last_read = r.get("last_read_seq") if self._schema == "staging" else r.get("last_read_at")
        return ChatEntityRow(
            chat_id=r["chat_id"],
            user_id=r["user_id"],
            joined_at=float(r["joined_at"]),
            last_read_at=float(last_read) if last_read is not None else None,
            muted=bool(r.get("muted", False)),
            mute_until=float(r["mute_until"]) if r.get("mute_until") is not None else None,
        )

    def _t(self) -> Any:
        return self._client.table(route_for_schema(_REPO_ENTITY, _CHAT_MEMBER_TABLES, self._schema))

    def _latest_message_seq(self, chat_id: str) -> int:
        response = (
            q.order(
                self._client.table(route_for_schema(_REPO_MSG, _MESSAGE_TABLES, self._schema)).select("seq").eq("chat_id", chat_id),
                "seq",
                desc=True,
                repo=_REPO_ENTITY,
                operation="latest_message_seq",
            )
            .limit(1)
            .execute()
        )
        rows = q.rows(response, _REPO_ENTITY, "latest_message_seq")
        if not rows:
            return 0
        return int(rows[0].get("seq") or 0)


class SupabaseChatMessageRepo:
    """Chat message persistence backed by Supabase."""

    def __init__(self, client: Any, *, schema: str | None = None) -> None:
        self._client = q.validate_client(client, _REPO_MSG)
        self._schema = resolve_runtime_schema(schema)

    def close(self) -> None:
        return None

    def create(self, row: ChatMessageRow) -> None:
        if self._schema == "staging":
            seq = self._next_seq(row.chat_id)
            payload = {
                "id": row.id,
                "chat_id": row.chat_id,
                "seq": seq,
                "sender_user_id": row.sender_id,
                "content": row.content,
                "mentions_json": row.mentioned_ids or [],
                "created_at": row.created_at,
            }
        else:
            payload = {
                "id": row.id,
                "chat_id": row.chat_id,
                "sender_id": row.sender_id,
                "content": row.content,
                "mentions": json.dumps(row.mentioned_ids) if row.mentioned_ids else json.dumps([]),
                "created_at": row.created_at,
            }
        self._t().insert(payload).execute()

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

    def list_unread(self, chat_id: str, user_id: str) -> list[ChatMessageRow]:
        """Return unread messages (after last_read_at, excluding own) in chronological order."""
        if self._schema == "staging":
            last_read = self._last_read_seq(chat_id, user_id)
            query = self._t().select("*").eq("chat_id", chat_id).neq("sender_user_id", user_id)
            query = q.gt(query, "seq", last_read, _REPO_MSG, "list_unread")
            query = q.order(query, "seq", desc=False, repo=_REPO_MSG, operation="list_unread")
            raw = q.rows(query.execute(), _REPO_MSG, "list_unread")
            return [self._to_msg(r) for r in raw]

        # Fetch last_read_at for this user in this chat.
        resp_ce = self._client.table(_TABLE_CHAT_ENTITIES).select("last_read_at").eq("chat_id", chat_id).eq("user_id", user_id).execute()
        ce_rows = q.rows(resp_ce, _REPO_MSG, "list_unread(last_read_at)")
        last_read: float | None = None
        if ce_rows:
            val = ce_rows[0].get("last_read_at")
            last_read = float(val) if val is not None else None

        query = self._t().select("*").eq("chat_id", chat_id).neq("sender_id", user_id)
        if last_read is not None:
            query = q.gt(query, "created_at", last_read, _REPO_MSG, "list_unread")
        query = q.order(query, "created_at", desc=False, repo=_REPO_MSG, operation="list_unread")
        raw = q.rows(query.execute(), _REPO_MSG, "list_unread")
        return [self._to_msg(r) for r in raw]

    def count_unread(self, chat_id: str, user_id: str) -> int:
        if self._schema == "staging":
            return len(self.list_unread(chat_id, user_id))

        # Fetch last_read_at for this user in this chat.
        resp_ce = self._client.table(_TABLE_CHAT_ENTITIES).select("last_read_at").eq("chat_id", chat_id).eq("user_id", user_id).execute()
        ce_rows = q.rows(resp_ce, _REPO_MSG, "count_unread(last_read_at)")
        if not ce_rows:
            return 0
        val = ce_rows[0].get("last_read_at")
        last_read: float | None = float(val) if val is not None else None

        query = self._t().select("id", count="exact").eq("chat_id", chat_id).neq("sender_id", user_id)
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

    def has_unread_mention(self, chat_id: str, user_id: str) -> bool:
        for message in self.list_unread(chat_id, user_id):
            if user_id in message.mentioned_ids:
                return True
        return False

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
        sender_id = r.get("sender_user_id") if self._schema == "staging" else r.get("sender_id")
        mentions_raw = r.get("mentions_json") if self._schema == "staging" else r.get("mentions")
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
            sender_id=sender_id,
            content=r["content"],
            mentioned_ids=mentioned,
            created_at=float(r["created_at"]),
        )

    def _t(self) -> Any:
        return self._client.table(route_for_schema(_REPO_MSG, _MESSAGE_TABLES, self._schema))

    def _next_seq(self, chat_id: str) -> int:
        response = self._client.rpc("increment_chat_message_seq", {"p_chat_id": chat_id}).execute()
        data = getattr(response, "data", None)
        if isinstance(data, int):
            return data
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                return int(first.get("value") or first.get("increment_chat_message_seq") or 0)
            return int(first)
        raise RuntimeError("Supabase chat message repo expected increment_chat_message_seq RPC data.")

    def _last_read_seq(self, chat_id: str, user_id: str) -> int:
        response = (
            self._client.table(route_for_schema(_REPO_ENTITY, _CHAT_MEMBER_TABLES, self._schema))
            .select("last_read_seq")
            .eq("chat_id", chat_id)
            .eq("user_id", user_id)
            .execute()
        )
        rows = q.rows(response, _REPO_MSG, "last_read_seq")
        if not rows:
            return 0
        return int(rows[0].get("last_read_seq") or 0)
