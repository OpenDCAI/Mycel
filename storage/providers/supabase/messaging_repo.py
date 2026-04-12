"""Supabase implementations for messaging v2 repos."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from messaging._utils import now_iso
from messaging.contracts import RelationshipState
from storage.providers.supabase import _query as q

logger = logging.getLogger(__name__)


class SupabaseChatMemberRepo:
    """chat_members table for Supabase messaging."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def close(self) -> None:
        pass

    def add_member(self, chat_id: str, user_id: str) -> None:
        self._client.table("chat_members").upsert(
            {"chat_id": chat_id, "user_id": user_id, "role": "member", "joined_at": time.time()},
            on_conflict="chat_id,user_id",
        ).execute()

    def list_members(self, chat_id: str) -> list[dict[str, Any]]:
        res = self._client.table("chat_members").select("*").eq("chat_id", chat_id).execute()
        return res.data or []

    def list_chats_for_user(self, user_id: str) -> list[str]:
        res = self._client.table("chat_members").select("chat_id").eq("user_id", user_id).execute()
        return [r["chat_id"] for r in (res.data or [])]

    def list_members_for_chats(self, chat_ids: list[str]) -> list[dict[str, Any]]:
        if not chat_ids:
            return []
        return q.rows_in_chunks(
            lambda: self._client.table("chat_members").select("chat_id,user_id,last_read_seq"),
            "chat_id",
            chat_ids,
            "chat member repo",
            "list_members_for_chats",
        )

    def is_member(self, chat_id: str, user_id: str) -> bool:
        res = self._client.table("chat_members").select("user_id").eq("chat_id", chat_id).eq("user_id", user_id).limit(1).execute()
        return bool(res.data)

    def find_chat_between(self, user_a: str, user_b: str) -> str | None:
        """Find the 1:1 chat between two users (exactly 2 members)."""
        # Fetch all chats for user_a, then find which has user_b as only other member
        chats_a = set(self.list_chats_for_user(user_a))
        chats_b = set(self.list_chats_for_user(user_b))
        common = chats_a & chats_b
        for chat_id in common:
            members = self.list_members(chat_id)
            if len(members) == 2:
                return chat_id
        return None

    def update_last_read(self, chat_id: str, user_id: str, last_read_seq: int) -> None:
        self._client.table("chat_members").update({"last_read_seq": last_read_seq}).eq("chat_id", chat_id).eq("user_id", user_id).execute()

    def last_read_seq(self, chat_id: str, user_id: str) -> int:
        member_res = (
            self._client.table("chat_members").select("last_read_seq").eq("chat_id", chat_id).eq("user_id", user_id).limit(1).execute()
        )
        if not member_res.data:
            return 0
        return int(member_res.data[0].get("last_read_seq") or 0)

    def update_mute(self, chat_id: str, user_id: str, muted: bool, mute_until: str | None = None) -> None:
        self._client.table("chat_members").update({"muted": muted, "mute_until": mute_until}).eq("chat_id", chat_id).eq(
            "user_id", user_id
        ).execute()


class SupabaseMessagesRepo:
    """messages table — rich message model for Supabase backend."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def close(self) -> None:
        pass

    def create(self, row: dict[str, Any], expected_read_seq: int | None = None) -> dict[str, Any]:
        """Insert a new message. Returns the created row."""
        if expected_read_seq is None:
            seq_response = self._client.rpc("increment_chat_message_seq", {"p_chat_id": row["chat_id"]}).execute()
            seq_data = seq_response.data
            if not seq_data:
                raise RuntimeError("Supabase messages repo expected increment_chat_message_seq RPC data.")
            if isinstance(seq_data, int):
                seq = seq_data
            else:
                seq_row = seq_data[0]
                seq = seq_row["increment_chat_message_seq"] if isinstance(seq_row, dict) else seq_row
        else:
            # @@@caught-up-send-cas - agent chat sends must prove the sender is still
            # acting on the latest seen chat state; otherwise sibling actors can fork
            # the conversation from the same stale history.
            next_seq = int(expected_read_seq) + 1
            update_res = (
                self._client.table("chats")
                .update({"next_message_seq": next_seq})
                .eq("id", row["chat_id"])
                .eq("next_message_seq", int(expected_read_seq))
                .execute()
            )
            if not update_res.data:
                raise RuntimeError(f"Chat advanced after your last read. Call read_messages(chat_id='{row['chat_id']}') first.")
            seq = next_seq
        payload = {**row, "seq": int(seq)}
        res = self._client.table("messages").insert(payload).execute()
        return res.data[0] if res.data else payload

    def get_by_id(self, message_id: str) -> dict[str, Any] | None:
        res = self._client.table("messages").select("*").eq("id", message_id).limit(1).execute()
        return res.data[0] if res.data else None

    def list_by_chat(
        self, chat_id: str, *, limit: int = 50, before: str | None = None, viewer_id: str | None = None
    ) -> list[dict[str, Any]]:
        q = self._client.table("messages").select("*").eq("chat_id", chat_id).is_("deleted_at", "null")
        if before:
            q = q.lt("seq", int(before))
        res = q.order("seq", desc=True).limit(limit).execute()
        rows = list(reversed(res.data or []))
        # Filter soft-deleted for viewer
        if viewer_id:
            rows = [r for r in rows if viewer_id not in (r.get("deleted_for") or [])]
        return rows

    def list_latest_by_chat_ids(self, chat_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not chat_ids:
            return {}
        latest_by_chat: dict[str, dict[str, Any]] = {}
        rows = q.rows_in_chunks(
            lambda: q.order(
                self._client.table("messages").select("*").is_("deleted_at", "null"),
                "seq",
                desc=True,
                repo="messages repo",
                operation="list_latest_by_chat_ids",
            ),
            "chat_id",
            chat_ids,
            "messages repo",
            "list_latest_by_chat_ids",
        )
        for row in rows:
            chat_id = str(row.get("chat_id") or "")
            if chat_id and chat_id not in latest_by_chat:
                latest_by_chat[chat_id] = row
        return latest_by_chat

    def list_unread(self, chat_id: str, user_id: str) -> list[dict[str, Any]]:
        """Messages after user's last_read_seq, excluding own, not deleted."""
        last_read_seq = self._last_read_seq(chat_id, user_id)

        q = self._client.table("messages").select("*").eq("chat_id", chat_id).neq("sender_user_id", user_id).is_("deleted_at", "null")
        if last_read_seq > 0:
            q = q.gt("seq", last_read_seq)
        res = q.order("seq", desc=False).execute()
        rows = res.data or []
        return [r for r in rows if user_id not in (r.get("deleted_for") or [])]

    def count_unread(self, chat_id: str, user_id: str) -> int:
        """Count unread messages using a COUNT query to avoid materializing rows."""
        last_read_seq = self._last_read_seq(chat_id, user_id)

        q = (
            self._client.table("messages")
            .select("id", count="exact")
            .eq("chat_id", chat_id)
            .neq("sender_user_id", user_id)
            .is_("deleted_at", "null")
        )
        if last_read_seq > 0:
            q = q.gt("seq", last_read_seq)
        res = q.execute()
        return res.count or 0

    def count_unread_by_chat_ids(self, user_id: str, last_read_by_chat: dict[str, int]) -> dict[str, int]:
        if not last_read_by_chat:
            return {}
        counts = {chat_id: 0 for chat_id in last_read_by_chat}
        min_last_read_seq = min(last_read_by_chat.values())

        def unread_query():
            query = self._client.table("messages").select("chat_id,seq").neq("sender_user_id", user_id).is_("deleted_at", "null")
            if min_last_read_seq > 0:
                query = query.gt("seq", min_last_read_seq)
            return query

        for row in q.rows_in_chunks(unread_query, "chat_id", list(last_read_by_chat), "messages repo", "count_unread_by_chat_ids"):
            chat_id = str(row.get("chat_id") or "")
            if int(row.get("seq") or 0) <= last_read_by_chat.get(chat_id, 0):
                continue
            counts[chat_id] += 1
        return counts

    def _last_read_seq(self, chat_id: str, user_id: str) -> int:
        member_res = (
            self._client.table("chat_members").select("last_read_seq").eq("chat_id", chat_id).eq("user_id", user_id).limit(1).execute()
        )
        if not member_res.data:
            return 0
        return int(member_res.data[0].get("last_read_seq") or 0)

    def retract(self, message_id: str, sender_id: str) -> bool:
        """Retract a message within 2-minute window."""

        msg = self.get_by_id(message_id)
        if not msg or msg.get("sender_user_id") != sender_id:
            return False
        created = msg.get("created_at")
        if created:
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                if datetime.now(tz=UTC) - created_dt > timedelta(minutes=2):
                    return False
            except (ValueError, AttributeError):
                pass
        self._client.table("messages").update({"retracted_at": now_iso(), "content": "[已撤回]"}).eq("id", message_id).execute()
        return True

    def delete_for(self, message_id: str, user_id: str) -> None:
        """Soft-delete for a specific user."""
        msg = self.get_by_id(message_id)
        if not msg:
            return
        deleted_for = list(msg.get("deleted_for") or [])
        if user_id not in deleted_for:
            deleted_for.append(user_id)
        self._client.table("messages").update({"deleted_for": deleted_for}).eq("id", message_id).execute()

    def search(self, query: str, *, chat_id: str, limit: int = 50) -> list[dict[str, Any]]:
        q = self._client.table("messages").select("*").ilike("content", f"%{query}%").is_("deleted_at", "null")
        q = q.eq("chat_id", chat_id)
        res = q.order("seq", desc=False).limit(limit).execute()
        return res.data or []

    def list_by_time_range(
        self, chat_id: str, *, after: str | None = None, before: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        q = self._client.table("messages").select("*").eq("chat_id", chat_id).is_("deleted_at", "null")
        if after:
            q = q.gte("created_at", after)
        if before:
            q = q.lte("created_at", before)
        res = q.order("created_at", desc=False).limit(limit).execute()
        return res.data or []


class SupabaseRelationshipRepo:
    """relationships table — Hire/Visit state machine persistence."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def close(self) -> None:
        pass

    def _ordered(self, a: str, b: str) -> tuple[str, str]:
        return (a, b) if a < b else (b, a)

    def _relationship_id(self, user_low: str, user_high: str, kind: str = "hire_visit") -> str:
        return f"{kind}:{user_low}:{user_high}"

    def _normalize(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(row)
        normalized.setdefault("kind", "hire_visit")
        normalized.setdefault("id", self._relationship_id(normalized["user_low"], normalized["user_high"], normalized["kind"]))
        return normalized

    def get(self, user_a: str, user_b: str) -> dict[str, Any] | None:
        user_low, user_high = self._ordered(user_a, user_b)
        res = (
            self._client.table("relationships")
            .select("*")
            .eq("user_low", user_low)
            .eq("user_high", user_high)
            .eq("kind", "hire_visit")
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        return self._normalize(res.data[0])

    def get_by_id(self, relationship_id: str) -> dict[str, Any] | None:
        parts = relationship_id.split(":", 2)
        if len(parts) != 3:
            return None
        kind, user_low, user_high = parts
        res = (
            self._client.table("relationships")
            .select("*")
            .eq("user_low", user_low)
            .eq("user_high", user_high)
            .eq("kind", kind)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        return self._normalize(res.data[0])

    def upsert(
        self,
        user_a: str,
        user_b: str,
        *,
        state: RelationshipState,
        initiator_user_id: str | None,
    ) -> dict[str, Any]:
        user_low, user_high = self._ordered(user_a, user_b)
        existing = self.get(user_a, user_b)
        now = time.time()
        if existing:
            relationship_updates = {"state": state, "initiator_user_id": initiator_user_id}
            if state == "none":
                (
                    self._client.table("relationships")
                    .delete()
                    .eq("user_low", user_low)
                    .eq("user_high", user_high)
                    .eq("kind", "hire_visit")
                    .execute()
                )
                return self._normalize({**existing, "updated_at": now, **relationship_updates})
            res = (
                self._client.table("relationships")
                .update({"updated_at": now, **relationship_updates})
                .eq("user_low", user_low)
                .eq("user_high", user_high)
                .eq("kind", "hire_visit")
                .execute()
            )
            return self._normalize(res.data[0] if res.data else {**existing, "updated_at": now, **relationship_updates})

        row = {
            "user_low": user_low,
            "user_high": user_high,
            "kind": "hire_visit",
            "created_at": now,
            "updated_at": now,
            "state": state,
            "initiator_user_id": initiator_user_id,
        }
        res = self._client.table("relationships").insert(row).execute()
        return self._normalize(res.data[0] if res.data else row)

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        # Single query with OR filter
        res = self._client.table("relationships").select("*").or_(f"user_low.eq.{user_id},user_high.eq.{user_id}").execute()
        return [self._normalize(raw) for raw in (res.data or [])]
