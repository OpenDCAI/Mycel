"""Chat tool service — 7 tools for entity-to-entity communication.

Tools use entity_ids as parameters.
Two entities share at most one chat; the system auto-resolves entity_id -> chat.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry

logger = logging.getLogger(__name__)

# @@@range-parser — parse range strings for chat_read history queries.
# Supports: negative index (-10:-1), relative time (-2h:, -1d:-6h), ISO dates (2026-03-20:2026-03-22).
_RELATIVE_RE = re.compile(r"^-(\d+)([hdm])$")


def _parse_range(range_str: str) -> dict:
    """Parse a range string into query parameters.

    Returns dict with either:
      {"type": "index", "limit": int, "skip_last": int}
      {"type": "time", "after": float|None, "before": float|None}
    Raises ValueError on invalid input.
    """
    # @@@range-split — split on ':' but ISO dates (YYYY-MM-DD) don't contain ':' so it's safe.
    # We only support date-level ISO (no HH:MM) to avoid ':' collision. Use -Nh/-Nm for sub-day precision.
    parts = range_str.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid range format '{range_str}'. Use 'start:end' (e.g. '-10:-1', '-1h:').")

    left, right = parts[0].strip(), parts[1].strip()

    # --- Detect index range: both parts are negative integers (or empty) ---
    left_is_neg_int = bool(re.match(r"^-\d+$", left)) if left else True
    right_is_neg_int = bool(re.match(r"^-\d+$", right)) if right else True
    # Reject positive integers
    left_is_pos_int = bool(re.match(r"^\d+$", left)) if left else False
    right_is_pos_int = bool(re.match(r"^\d+$", right)) if right else False
    if left_is_pos_int or right_is_pos_int:
        raise ValueError("Positive indices not allowed. Use negative indices like '-10:-1'.")

    if left_is_neg_int and right_is_neg_int and not _RELATIVE_RE.match(left or "") and not _RELATIVE_RE.match(right or ""):
        # Pure negative integer range
        start = int(left) if left else None  # e.g. -10
        end = int(right) if right else None  # e.g. -1
        if start is not None and end is not None:
            if start >= end:
                raise ValueError(f"Start ({start}) must be less than end ({end}). E.g. '-10:-1'.")
            limit = end - start
            skip_last = -end  # -1 means skip 0 from the end, -5 means skip 4
        elif start is not None:
            limit = -start
            skip_last = 0
        else:
            limit = -end if end else 20
            skip_last = 0
        return {"type": "index", "limit": limit, "skip_last": skip_last}

    # --- Time range: relative (-2h, -1d) or ISO date ---
    now = time.time()
    after_ts = _parse_time_endpoint(left, now) if left else None
    before_ts = _parse_time_endpoint(right, now) if right else None
    if after_ts is None and before_ts is None:
        raise ValueError(f"Invalid range '{range_str}'. Use '-10:-1', '-1h:', or '2026-03-20:'.")
    return {"type": "time", "after": after_ts, "before": before_ts}


def _parse_time_endpoint(s: str, now: float) -> float | None:
    """Parse a single time endpoint: relative (-2h, -1d, -30m) or ISO date."""
    m = _RELATIVE_RE.match(s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        seconds = {"h": 3600, "d": 86400, "m": 60}[unit]
        return now - n * seconds
    # Try ISO date parsing (date-level only — no HH:MM to avoid ':' collision with range separator)
    try:
        dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        pass
    raise ValueError(f"Cannot parse time '{s}'. Use '-2h', '-1d', '-30m', or '2026-03-20'.")


class ChatToolService:
    """Registers 5 chat tools into ToolRegistry.

    Each tool closure captures entity_id (the calling agent's identity).
    """

    def __init__(
        self,
        registry: ToolRegistry,
        entity_id: str,
        owner_entity_id: str,
        *,
        entity_repo: Any = None,
        chat_service: Any = None,
        chat_entity_repo: Any = None,
        chat_message_repo: Any = None,
        member_repo: Any = None,
        chat_event_bus: Any = None,
        runtime_fn: Any = None,
    ) -> None:
        self._entity_id = entity_id
        self._owner_entity_id = owner_entity_id
        self._entities = entity_repo
        self._chat_service = chat_service
        self._chat_entities = chat_entity_repo
        self._messages = chat_message_repo
        self._members = member_repo
        self._event_bus = chat_event_bus
        self._runtime_fn = runtime_fn  # callable → AgentRuntime (lazy, resolves at call time)
        self._register(registry)

    def _register(self, registry: ToolRegistry) -> None:
        self._register_chats(registry)
        self._register_chat_read(registry)
        self._register_chat_send(registry)
        self._register_chat_search(registry)
        self._register_directory(registry)

    def _format_msgs(self, msgs: list, eid: str) -> str:
        lines = []
        for m in msgs:
            sender = self._entities.get_by_id(m.sender_entity_id)
            name = sender.name if sender else "unknown"
            tag = "you" if m.sender_entity_id == eid else name
            lines.append(f"[{tag}]: {m.content}")
        return "\n".join(lines)

    def _fetch_by_range(self, chat_id: str, parsed: dict) -> list:
        if parsed["type"] == "index":
            limit = parsed["limit"]
            skip_last = parsed["skip_last"]
            # Fetch limit + skip_last, then trim the tail
            fetch_count = limit + skip_last
            msgs = self._messages.list_by_chat(chat_id, limit=fetch_count)
            if skip_last > 0:
                msgs = msgs[:len(msgs) - skip_last] if len(msgs) > skip_last else []
            return msgs
        else:
            return self._messages.list_by_time_range(
                chat_id, after=parsed["after"], before=parsed["before"],
            )

    def _register_chats(self, registry: ToolRegistry) -> None:
        eid = self._entity_id

        def handle(unread_only: bool = False, limit: int = 20) -> str:
            chats = self._chat_service.list_chats_for_entity(eid)
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
                    id_str = f" [entity_id: {other_id}]" if other_id else ""
                lines.append(f"- {name}{id_str}{unread_str}{last_preview}")
            return "\n".join(lines)

        registry.register(ToolEntry(
            name="chats",
            mode=ToolMode.INLINE,
            schema={
                "name": "chats",
                "description": "List your chats. Returns chat summaries with entity_ids of participants.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "unread_only": {"type": "boolean", "description": "Only show chats with unread messages", "default": False},
                        "limit": {"type": "integer", "description": "Max number of chats to return", "default": 20},
                    },
                },
            },
            handler=handle,
            source="chat",
        ))

    def _register_chat_read(self, registry: ToolRegistry) -> None:
        eid = self._entity_id

        def handle(entity_id: str | None = None, chat_id: str | None = None,
                   range: str | None = None) -> str:
            if chat_id:
                pass  # use chat_id directly
            elif entity_id:
                chat_id = self._chat_entities.find_chat_between(eid, entity_id)
                if not chat_id:
                    target = self._entities.get_by_id(entity_id)
                    name = target.name if target else entity_id
                    return f"No chat history with {name}."
            else:
                return "Provide entity_id or chat_id."

            # @@@range-dispatch — if range is provided, use it regardless of unread state.
            if range:
                try:
                    parsed = _parse_range(range)
                except ValueError as e:
                    return str(e)
                msgs = self._fetch_by_range(chat_id, parsed)
                if not msgs:
                    return "No messages in that range."
                # @@@range-marks-read — WORKAROUND: unblock chat_send by pushing
                # last_read_at to now. This marks ALL messages as read, not just
                # the requested range. Proper fix needs per-message read tracking
                # instead of the current single-timestamp waterline model.
                self._chat_entities.update_last_read(chat_id, eid, time.time())
                return self._format_msgs(msgs, eid)

            # @@@read-unread-only — default to unread messages only.
            msgs = self._messages.list_unread(chat_id, eid)
            if msgs:
                self._chat_entities.update_last_read(chat_id, eid, time.time())
                return self._format_msgs(msgs, eid)

            # Nothing unread — prompt agent to use range parameter
            return (
                "No unread messages. To read history, call again with range:\n"
                "  range='-10:-1'  (last 10 messages)\n"
                "  range='-5:'     (last 5 messages)\n"
                "  range='-1h:'    (last hour)\n"
                "  range='-2d:-1d' (yesterday)\n"
                "  range='2026-03-20:2026-03-22' (date range)"
            )

        registry.register(ToolEntry(
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
                        "range": {"type": "string", "description": "History range. Negative index '-X:-Y' or time '-1h:', '2026-03-20:'. Positive indices NOT allowed."},
                    },
                },
            },
            handler=handle,
            source="chat",
        ))

    def _register_chat_send(self, registry: ToolRegistry) -> None:
        eid = self._entity_id

        def handle(content: str, entity_id: str | None = None, chat_id: str | None = None,
                   signal: str = "open", mentions: list[str] | None = None) -> str:
            # @@@read-before-write — resolve chat_id, then check unread
            resolved_chat_id = chat_id
            target_name = "chat"

            if chat_id:
                if not self._chat_entities.is_entity_in_chat(chat_id, eid):
                    raise RuntimeError(f"You are not a member of chat {chat_id}")
            elif entity_id:
                if entity_id == eid:
                    raise RuntimeError("Cannot send a message to yourself.")
                target = self._entities.get_by_id(entity_id)
                if not target:
                    raise RuntimeError(f"Entity not found: {entity_id}")
                target_name = target.name
                resolved_chat_id = self._chat_entities.find_chat_between(eid, entity_id)
                if not resolved_chat_id:
                    # New chat — no unread possible, create and send
                    chat = self._chat_service.find_or_create_chat([eid, entity_id])
                    resolved_chat_id = chat.id
            else:
                raise RuntimeError("Provide entity_id (for 1:1) or chat_id (for group)")

            # @@@read-before-write-gate — reject if unread messages exist
            unread = self._messages.count_unread(resolved_chat_id, eid)
            if unread > 0:
                raise RuntimeError(
                    f"You have {unread} unread message(s). "
                    f"Call chat_read(chat_id='{resolved_chat_id}') first."
                )

            # Append signal to content (for chat_read) + pass through chain (for notification)
            effective_signal = signal if signal in ("yield", "close") else None
            if effective_signal:
                content = f"{content}\n[signal: {effective_signal}]"

            self._chat_service.send_message(resolved_chat_id, eid, content, mentions,
                                            signal=effective_signal)
            return f"Message sent to {target_name}."

        registry.register(ToolEntry(
            name="chat_send",
            mode=ToolMode.INLINE,
            schema={
                "name": "chat_send",
                "description": (
                    "Send a message. Use entity_id for 1:1 chats, chat_id for group chats.\n\n"
                    "You MUST call chat_read() first if you have unread messages — sending will fail otherwise.\n\n"
                    "Signal protocol — append to content:\n"
                    "  (no tag) = I expect a reply from you\n"
                    "  ::yield = I'm done with my turn; reply only if you want to\n"
                    "  ::close = conversation over, do NOT reply\n\n"
                    "For games/turns: do NOT append ::yield — just send the move and expect a reply."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "Message content"},
                        "entity_id": {"type": "string", "description": "Target entity_id (for 1:1 chat)"},
                        "chat_id": {"type": "string", "description": "Target chat_id (for group chat)"},
                        "signal": {"type": "string", "enum": ["open", "yield", "close"], "description": "Signal intent to recipient", "default": "open"},
                        "mentions": {"type": "array", "items": {"type": "string"}, "description": "Entity IDs to @mention (overrides mute for these recipients)"},
                    },
                    "required": ["content"],
                },
            },
            handler=handle,
            source="chat",
        ))

    def _register_chat_search(self, registry: ToolRegistry) -> None:
        eid = self._entity_id

        def handle(query: str, entity_id: str | None = None) -> str:
            chat_id = None
            if entity_id:
                chat_id = self._chat_entities.find_chat_between(eid, entity_id)
            results = self._messages.search(query, chat_id=chat_id, limit=20)
            if not results:
                return f"No messages matching '{query}'."
            lines = []
            for m in results:
                sender = self._entities.get_by_id(m.sender_entity_id)
                name = sender.name if sender else "unknown"
                lines.append(f"[{name}] {m.content[:100]}")
            return "\n".join(lines)

        registry.register(ToolEntry(
            name="chat_search",
            mode=ToolMode.INLINE,
            schema={
                "name": "chat_search",
                "description": "Search messages. Optionally filter by entity_id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "entity_id": {"type": "string", "description": "Optional: only search in chat with this entity"},
                    },
                    "required": ["query"],
                },
            },
            handler=handle,
            source="chat",
        ))

    def _register_directory(self, registry: ToolRegistry) -> None:
        eid = self._entity_id

        def handle(search: str | None = None, type: str | None = None) -> str:
            all_entities = self._entities.list_all()
            entities = [e for e in all_entities if e.id != eid]
            if type:
                entities = [e for e in entities if e.type == type]
            if search:
                q = search.lower()
                entities = [e for e in entities if q in e.name.lower()]
            if not entities:
                return "No entities found."
            lines = []
            for e in entities:
                member = self._members.get_by_id(e.member_id)
                owner_info = ""
                if e.type == "agent" and member and member.owner_id:
                    owner_member = self._members.get_by_id(member.owner_id)
                    if owner_member:
                        owner_info = f" (owner: {owner_member.name})"
                lines.append(f"- {e.name} [{e.type}] entity_id={e.id}{owner_info}")
            return "\n".join(lines)

        registry.register(ToolEntry(
            name="directory",
            mode=ToolMode.INLINE,
            schema={
                "name": "directory",
                "description": "Browse the entity directory. Returns entity_ids for use with chat_send, chat_read.",
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
        ))


