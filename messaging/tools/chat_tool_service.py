"""Chat tool service (messaging module version).

Provides 5 tools: chats, chat_read, chat_send, chat_search, directory.
directory includes privacy filter: only shows entities with existing relationships.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry

logger = logging.getLogger(__name__)

_RELATIVE_RE = re.compile(r"^-(\d+)([hdm])$")


def _parse_range(range_str: str) -> dict:
    parts = range_str.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid range format '{range_str}'. Use 'start:end' (e.g. '-10:-1', '-1h:').")
    left, right = parts[0].strip(), parts[1].strip()
    left_is_neg_int = bool(re.match(r"^-\d+$", left)) if left else True
    right_is_neg_int = bool(re.match(r"^-\d+$", right)) if right else True
    left_is_pos_int = bool(re.match(r"^\d+$", left)) if left else False
    right_is_pos_int = bool(re.match(r"^\d+$", right)) if right else False
    if left_is_pos_int or right_is_pos_int:
        raise ValueError("Positive indices not allowed. Use negative indices like '-10:-1'.")
    if left_is_neg_int and right_is_neg_int and not _RELATIVE_RE.match(left or "") and not _RELATIVE_RE.match(right or ""):
        start = int(left) if left else None
        end = int(right) if right else None
        if start is not None and end is not None:
            if start >= end:
                raise ValueError(f"Start ({start}) must be less than end ({end}). E.g. '-10:-1'.")
            limit = end - start
            skip_last = -end
        elif start is not None:
            limit = -start
            skip_last = 0
        else:
            limit = -end if end else 20
            skip_last = 0
        return {"type": "index", "limit": limit, "skip_last": skip_last}
    now = time.time()
    after_ts = _parse_time_endpoint(left, now) if left else None
    before_ts = _parse_time_endpoint(right, now) if right else None
    if after_ts is None and before_ts is None:
        raise ValueError(f"Invalid range '{range_str}'. Use '-10:-1', '-1h:', or '2026-03-20:'.")
    return {"type": "time", "after": after_ts, "before": before_ts}


def _parse_time_endpoint(s: str, now: float) -> float | None:
    m = _RELATIVE_RE.match(s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return now - n * {"h": 3600, "d": 86400, "m": 60}[unit]
    try:
        dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)
        return dt.timestamp()
    except ValueError:
        pass
    raise ValueError(f"Cannot parse time '{s}'. Use '-2h', '-1d', '-30m', or '2026-03-20'.")


def _float_ts(ts: Any) -> float | None:
    """Convert ISO string or float timestamp to float."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


class ChatToolService:
    """Registers 5 chat tools into ToolRegistry (messaging module version)."""

    def __init__(
        self,
        registry: ToolRegistry,
        user_id: str,
        owner_id: str,
        *,
        entity_repo: Any = None,
        messaging_service: Any = None,  # MessagingService (new)
        chat_member_repo: Any = None,  # SupabaseChatMemberRepo
        messages_repo: Any = None,  # SupabaseMessagesRepo
        member_repo: Any = None,
        relationship_repo: Any = None,  # for directory privacy filter
    ) -> None:
        self._user_id = user_id
        self._owner_id = owner_id
        self._entities = entity_repo
        self._messaging = messaging_service
        self._chat_members = chat_member_repo
        self._messages = messages_repo
        self._member_repo = member_repo
        self._relationships = relationship_repo
        self._register(registry)

    def _register(self, registry: ToolRegistry) -> None:
        self._register_chats(registry)
        self._register_chat_read(registry)
        self._register_chat_send(registry)
        self._register_chat_search(registry)
        self._register_directory(registry)

    def _format_msgs(self, msgs: list[dict], eid: str) -> str:
        lines = []
        for m in msgs:
            sender = self._entities.get_by_id(m.get("sender_id", ""))
            name = sender.name if sender else "unknown"
            tag = "you" if m.get("sender_id") == eid else name
            content = m.get("content", "")
            if m.get("retracted_at"):
                content = "[已撤回]"
            lines.append(f"[{tag}]: {content}")
        return "\n".join(lines)

    def _fetch_by_range(self, chat_id: str, parsed: dict) -> list[dict]:
        if parsed["type"] == "index":
            limit = parsed["limit"]
            skip_last = parsed["skip_last"]
            fetch_count = limit + skip_last
            msgs = self._messages.list_by_chat(chat_id, limit=fetch_count, viewer_id=self._user_id)
            if skip_last > 0:
                msgs = msgs[: len(msgs) - skip_last] if len(msgs) > skip_last else []
            return msgs
        else:
            after_iso = datetime.fromtimestamp(parsed["after"], tz=UTC).isoformat() if parsed.get("after") else None
            before_iso = datetime.fromtimestamp(parsed["before"], tz=UTC).isoformat() if parsed.get("before") else None
            return self._messages.list_by_time_range(chat_id, after=after_iso, before=before_iso)

    def _register_chats(self, registry: ToolRegistry) -> None:
        eid = self._user_id

        def handle(unread_only: bool = False, limit: int = 20) -> str:
            chats = self._messaging.list_chats_for_user(eid)
            if unread_only:
                chats = [c for c in chats if c.get("unread_count", 0) > 0]
            chats = chats[:limit]
            if not chats:
                return "No chats found."
            lines = []
            for c in chats:
                others = [e for e in c.get("entities", []) if e["id"] != eid]
                name = ", ".join(e["name"] for e in others) or "Unknown"
                unread = c.get("unread_count", 0)
                last = c.get("last_message")
                last_preview = f' — last: "{last["content"][:50]}"' if last else ""
                unread_str = f" ({unread} unread)" if unread > 0 else ""
                is_group = len(others) >= 2
                if is_group:
                    id_str = f" [chat_id: {c['id']}]"
                else:
                    other_id = others[0]["id"] if others else ""
                    id_str = f" [id: {other_id}]" if other_id else ""
                lines.append(f"- {name}{id_str}{unread_str}{last_preview}")
            return "\n".join(lines)

        registry.register(
            ToolEntry(
                name="chats",
                mode=ToolMode.INLINE,
                schema={
                    "name": "chats",
                    "description": "List your chats. Returns chat summaries with user_ids of participants.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "unread_only": {
                                "type": "boolean",
                                "description": "Only show chats with unread messages",
                                "default": False,
                            },
                            "limit": {"type": "integer", "description": "Max number of chats to return", "default": 20},
                        },
                    },
                },
                handler=handle,
                source="chat",
            )
        )

    def _register_chat_read(self, registry: ToolRegistry) -> None:
        eid = self._user_id

        def handle(entity_id: str | None = None, chat_id: str | None = None, range: str | None = None) -> str:
            if chat_id:
                pass
            elif entity_id:
                chat_id = self._chat_members.find_chat_between(eid, entity_id)
                if not chat_id:
                    target = self._entities.get_by_id(entity_id)
                    name = target.name if target else entity_id
                    return f"No chat history with {name}."
            else:
                return "Provide entity_id or chat_id."

            if range:
                try:
                    parsed = _parse_range(range)
                except ValueError as e:
                    return str(e)
                msgs = self._fetch_by_range(chat_id, parsed)
                if not msgs:
                    return "No messages in that range."
                self._messaging.mark_read(chat_id, eid)
                return self._format_msgs(msgs, eid)

            msgs = self._messaging.list_unread(chat_id, eid)
            if msgs:
                self._messaging.mark_read(chat_id, eid)
                return self._format_msgs(msgs, eid)

            return (
                "No unread messages. To read history, call again with range:\n"
                "  range='-10:-1'  (last 10 messages)\n"
                "  range='-5:'     (last 5 messages)\n"
                "  range='-1h:'    (last hour)\n"
                "  range='-2d:-1d' (yesterday)\n"
                "  range='2026-03-20:2026-03-22' (date range)"
            )

        registry.register(
            ToolEntry(
                name="chat_read",
                mode=ToolMode.INLINE,
                schema={
                    "name": "chat_read",
                    "description": (
                        "Read chat messages. Returns unread messages by default.\n"
                        "If nothing unread, use range to read history:\n"
                        "  Negative index: '-10:-1' (last 10), '-5:' (last 5)\n"
                        "  Time interval: '-1h:', '-2d:-1d', '2026-03-20:2026-03-22'\n"
                        "Positive indices are NOT allowed."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "entity_id": {"type": "string", "description": "Entity_id for 1:1 chat history"},
                            "chat_id": {"type": "string", "description": "Chat_id for group chat history"},
                            "range": {
                                "type": "string",
                                "description": "History range. Negative index '-X:-Y' or time '-1h:', '2026-03-20:'.",
                            },
                        },
                    },
                },
                handler=handle,
                source="chat",
            )
        )

    def _register_chat_send(self, registry: ToolRegistry) -> None:
        eid = self._user_id

        def handle(
            content: str,
            entity_id: str | None = None,
            chat_id: str | None = None,
            signal: str = "open",
            mentions: list[str] | None = None,
        ) -> str:
            resolved_chat_id = chat_id
            target_name = "chat"

            if chat_id:
                if not self._chat_members.is_member(chat_id, eid):
                    raise RuntimeError(f"You are not a member of chat {chat_id}")
            elif entity_id:
                if entity_id == eid:
                    raise RuntimeError("Cannot send a message to yourself.")
                target = self._entities.get_by_id(entity_id)
                if not target:
                    raise RuntimeError(f"Entity not found: {entity_id}")
                target_name = target.name
                chat = self._messaging.find_or_create_chat([eid, entity_id])
                resolved_chat_id = chat["id"]
            else:
                raise RuntimeError("Provide entity_id (for 1:1) or chat_id (for group)")

            unread = self._messaging.count_unread(resolved_chat_id, eid)
            if unread > 0:
                raise RuntimeError(f"You have {unread} unread message(s). Call chat_read(chat_id='{resolved_chat_id}') first.")

            effective_signal = signal if signal in ("yield", "close") else None
            if effective_signal:
                content = f"{content}\n[signal: {effective_signal}]"

            self._messaging.send(resolved_chat_id, eid, content, mentions=mentions, signal=effective_signal)
            return f"Message sent to {target_name}."

        registry.register(
            ToolEntry(
                name="chat_send",
                mode=ToolMode.INLINE,
                schema={
                    "name": "chat_send",
                    "description": (
                        "Send a message. Use entity_id for 1:1 chats, chat_id for group chats.\n\n"
                        "You MUST call chat_read() first if you have unread messages — sending will fail otherwise.\n\n"
                        "Signal protocol:\n"
                        "  (no tag) = I expect a reply from you\n"
                        "  ::yield = I'm done with my turn; reply only if you want to\n"
                        "  ::close = conversation over, do NOT reply"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "Message content"},
                            "entity_id": {"type": "string", "description": "Target entity_id (for 1:1 chat)"},
                            "chat_id": {"type": "string", "description": "Target chat_id (for group chat)"},
                            "signal": {"type": "string", "enum": ["open", "yield", "close"], "default": "open"},
                            "mentions": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Entity IDs to @mention",
                            },
                        },
                        "required": ["content"],
                    },
                },
                handler=handle,
                source="chat",
            )
        )

    def _register_chat_search(self, registry: ToolRegistry) -> None:
        eid = self._user_id

        def handle(query: str, entity_id: str | None = None) -> str:
            chat_id = None
            if entity_id:
                chat_id = self._chat_members.find_chat_between(eid, entity_id)
            results = self._messaging.search_messages(query, chat_id=chat_id)
            if not results:
                return f"No messages matching '{query}'."
            lines = []
            for m in results:
                sender = self._entities.get_by_id(m.get("sender_id", ""))
                name = sender.name if sender else "unknown"
                lines.append(f"[{name}] {m.get('content', '')[:100]}")
            return "\n".join(lines)

        registry.register(
            ToolEntry(
                name="chat_search",
                mode=ToolMode.INLINE,
                schema={
                    "name": "chat_search",
                    "description": "Search messages. Optionally filter by entity_id.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "entity_id": {
                                "type": "string",
                                "description": "Optional: only search in chat with this entity",
                            },
                        },
                        "required": ["query"],
                    },
                },
                handler=handle,
                source="chat",
            )
        )

    def _register_directory(self, registry: ToolRegistry) -> None:
        eid = self._user_id

        def handle(search: str | None = None, type: str | None = None) -> str:
            all_entities = self._entities.list_all()
            entities = [e for e in all_entities if e.id != eid]
            if type:
                entities = [e for e in entities if e.type == type]
            if search:
                q = search.lower()
                entities = [e for e in entities if q in e.name.lower()]

            # Privacy filter: only show entities with a relationship (VISIT or HIRE)
            # or entities owned by the same user (owner_id)
            if self._relationships:

                def _is_visible(e) -> bool:
                    # Same owner → always visible
                    if hasattr(e, "member_id"):
                        mem = self._member_repo.get_by_id(e.member_id) if self._member_repo else None
                        if mem and getattr(mem, "owner_user_id", None) == getattr(
                            self._entities.get_by_id(self._owner_id), "member_id", None
                        ):
                            return True
                    rel = self._relationships.get(eid, e.id)
                    if rel and rel.get("state") in ("visit", "hire"):
                        return True
                    return False

                entities = [e for e in entities if _is_visible(e)]

            if not entities:
                return "No entities found."
            lines = []
            for e in entities:
                member = self._member_repo.get_by_id(e.member_id) if self._member_repo else None
                owner_info = ""
                if e.type == "agent" and member and getattr(member, "owner_user_id", None):
                    owner_member = self._member_repo.get_by_id(member.owner_user_id)
                    if owner_member:
                        owner_info = f" (owner: {owner_member.name})"
                lines.append(f"- {e.name} [{e.type}] entity_id={e.id}{owner_info}")
            return "\n".join(lines)

        registry.register(
            ToolEntry(
                name="directory",
                mode=ToolMode.INLINE,
                schema={
                    "name": "directory",
                    "description": "Browse the entity directory. Shows entities with Visit/Hire relationships. Returns user_ids for chat_send.",  # noqa: E501
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search": {"type": "string", "description": "Search by name"},
                            "type": {"type": "string", "description": "Filter by type: 'human' or 'agent'"},
                        },
                    },
                },
                handler=handle,
                source="chat",
            )
        )
