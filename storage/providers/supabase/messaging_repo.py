"""Supabase implementations for messaging v2 repos.

Covers: chats, chat_members, messages, message_reads, message_deliveries.
All IDs are TEXT (UUID strings) for consistency with existing SQLite schema.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from messaging._utils import now_iso

logger = logging.getLogger(__name__)


class SupabaseChatMemberRepo:
    """chat_members table — replaces SQLiteChatParticipantRepo for Supabase backend."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def close(self) -> None:
        pass

    def add_member(self, chat_id: str, user_id: str) -> None:
        self._client.table("chat_members").upsert(
            {"chat_id": chat_id, "user_id": user_id, "role": "member", "joined_at": now_iso()},
            on_conflict="chat_id,user_id",
        ).execute()

    def list_members(self, chat_id: str) -> list[dict[str, Any]]:
        res = self._client.table("chat_members").select("*").eq("chat_id", chat_id).execute()
        return res.data or []

    def list_chats_for_user(self, user_id: str) -> list[str]:
        res = self._client.table("chat_members").select("chat_id").eq("user_id", user_id).execute()
        return [r["chat_id"] for r in (res.data or [])]

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

    def update_last_read(self, chat_id: str, user_id: str) -> None:
        self._client.table("chat_members").update({"last_read_at": now_iso()}).eq("chat_id", chat_id).eq("user_id", user_id).execute()

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

    def create(self, row: dict[str, Any]) -> dict[str, Any]:
        """Insert a new message. Returns the created row."""
        res = self._client.table("messages").insert(row).execute()
        return res.data[0] if res.data else row

    def get_by_id(self, message_id: str) -> dict[str, Any] | None:
        res = self._client.table("messages").select("*").eq("id", message_id).limit(1).execute()
        return res.data[0] if res.data else None

    def list_by_chat(
        self, chat_id: str, *, limit: int = 50, before: str | None = None, viewer_id: str | None = None
    ) -> list[dict[str, Any]]:
        q = self._client.table("messages").select("*").eq("chat_id", chat_id).is_("deleted_at", "null")
        if before:
            q = q.lt("created_at", before)
        res = q.order("created_at", desc=True).limit(limit).execute()
        rows = list(reversed(res.data or []))
        # Filter soft-deleted for viewer
        if viewer_id:
            rows = [r for r in rows if viewer_id not in (r.get("deleted_for") or [])]
        return rows

    def list_unread(self, chat_id: str, user_id: str) -> list[dict[str, Any]]:
        """Messages after user's last_read_at, excluding own, not deleted."""
        # Get last_read_at from chat_members
        member_res = (
            self._client.table("chat_members").select("last_read_at").eq("chat_id", chat_id).eq("user_id", user_id).limit(1).execute()
        )
        last_read = None
        if member_res.data:
            last_read = member_res.data[0].get("last_read_at")

        q = self._client.table("messages").select("*").eq("chat_id", chat_id).neq("sender_id", user_id).is_("deleted_at", "null")
        if last_read:
            q = q.gt("created_at", last_read)
        res = q.order("created_at", desc=False).execute()
        rows = res.data or []
        return [r for r in rows if user_id not in (r.get("deleted_for") or [])]

    def count_unread(self, chat_id: str, user_id: str) -> int:
        """Count unread messages using a COUNT query to avoid materializing rows."""
        member_res = (
            self._client.table("chat_members").select("last_read_at").eq("chat_id", chat_id).eq("user_id", user_id).limit(1).execute()
        )
        last_read = None
        if member_res.data:
            last_read = member_res.data[0].get("last_read_at")

        q = (
            self._client.table("messages")
            .select("id", count="exact")
            .eq("chat_id", chat_id)
            .neq("sender_id", user_id)
            .is_("deleted_at", "null")
        )
        if last_read:
            q = q.gt("created_at", last_read)
        res = q.execute()
        return res.count or 0

    def retract(self, message_id: str, sender_id: str) -> bool:
        """Retract a message within 2-minute window."""

        msg = self.get_by_id(message_id)
        if not msg or msg.get("sender_id") != sender_id:
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

    def search(self, query: str, *, chat_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        q = self._client.table("messages").select("*").ilike("content", f"%{query}%").is_("deleted_at", "null")
        if chat_id:
            q = q.eq("chat_id", chat_id)
        res = q.order("created_at", desc=False).limit(limit).execute()
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


class SupabaseMessageReadRepo:
    """message_reads table — per-message read receipts."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def close(self) -> None:
        pass

    def mark_read(self, message_id: str, user_id: str) -> None:
        self._client.table("message_reads").upsert(
            {"message_id": message_id, "user_id": user_id, "read_at": now_iso()},
            on_conflict="message_id,user_id",
        ).execute()

    def mark_chat_read(self, chat_id: str, user_id: str, message_ids: list[str]) -> None:
        """Bulk mark messages as read."""
        rows = [{"message_id": mid, "user_id": user_id, "read_at": now_iso()} for mid in message_ids]
        if rows:
            self._client.table("message_reads").upsert(rows, on_conflict="message_id,user_id").execute()

    def get_read_count(self, message_id: str) -> int:
        res = self._client.table("message_reads").select("user_id", count="exact").eq("message_id", message_id).execute()
        return res.count or 0

    def has_read(self, message_id: str, user_id: str) -> bool:
        res = self._client.table("message_reads").select("user_id").eq("message_id", message_id).eq("user_id", user_id).limit(1).execute()
        return bool(res.data)


class SupabaseRelationshipRepo:
    """relationships table — Hire/Visit state machine persistence."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def close(self) -> None:
        pass

    def _ordered(self, a: str, b: str) -> tuple[str, str]:
        return (a, b) if a < b else (b, a)

    def get(self, user_a: str, user_b: str) -> dict[str, Any] | None:
        pa, pb = self._ordered(user_a, user_b)
        res = self._client.table("relationships").select("*").eq("principal_a", pa).eq("principal_b", pb).limit(1).execute()
        return res.data[0] if res.data else None

    def get_by_id(self, relationship_id: str) -> dict[str, Any] | None:
        res = self._client.table("relationships").select("*").eq("id", relationship_id).limit(1).execute()
        return res.data[0] if res.data else None

    def upsert(self, user_a: str, user_b: str, **fields: Any) -> dict[str, Any]:
        pa, pb = self._ordered(user_a, user_b)
        existing = self.get(user_a, user_b)
        now = now_iso()
        if existing:
            res = self._client.table("relationships").update({"updated_at": now, **fields}).eq("id", existing["id"]).execute()
            return res.data[0] if res.data else {**existing, "updated_at": now, **fields}
        else:
            import uuid

            row = {"id": str(uuid.uuid4()), "principal_a": pa, "principal_b": pb, "updated_at": now, **fields}
            res = self._client.table("relationships").insert(row).execute()
            return res.data[0] if res.data else row

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        # Single query with OR filter
        res = self._client.table("relationships").select("*").or_(f"principal_a.eq.{user_id},principal_b.eq.{user_id}").execute()
        return res.data or []
