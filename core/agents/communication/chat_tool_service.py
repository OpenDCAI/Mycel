"""Chat tool service — Mycel-native tools for user-to-user communication.

Tools use user_ids as parameters (human = Supabase auth UUID, agent = member_id).
Two users share at most one chat; the system auto-resolves user_id → chat.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry, make_tool_schema

logger = logging.getLogger(__name__)

# @@@range-parser — parse range strings for read_messages history queries.
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
        dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)
        return dt.timestamp()
    except ValueError:
        pass
    raise ValueError(f"Cannot parse time '{s}'. Use '-2h', '-1d', '-30m', or '2026-03-20'.")


class ChatToolService:
    """Registers the chat tool surface into ToolRegistry.

    Each tool closure captures user_id (the calling agent's social identity = member_id).
    """

    def __init__(
        self,
        registry: ToolRegistry,
        user_id: str,
        owner_user_id: str,
        *,
        chat_service: Any = None,
        chat_participant_repo: Any = None,
        chat_message_repo: Any = None,
        member_repo: Any = None,
        chat_event_bus: Any = None,
        runtime_fn: Any = None,
    ) -> None:
        self._user_id = user_id
        self._owner_user_id = owner_user_id
        self._chat_service = chat_service
        self._chat_participants = chat_participant_repo
        self._messages = chat_message_repo
        self._members = member_repo
        self._event_bus = chat_event_bus
        self._runtime_fn = runtime_fn  # callable → AgentRuntime (lazy, resolves at call time)
        self._register(registry)

    def _register(self, registry: ToolRegistry) -> None:
        self._register_list_chats(registry)
        self._register_read_messages(registry)
        self._register_send_message(registry)
        self._register_search_messages(registry)

    def _latest_notified_chat_id(self, request: Any) -> str | None:
        state = getattr(request, "state", None)
        messages = getattr(state, "messages", None)
        if not isinstance(messages, list):
            return None
        for message in reversed(messages):
            metadata = getattr(message, "metadata", None) or {}
            if metadata.get("source") != "external" or metadata.get("notification_type") != "chat":
                continue
            content = getattr(message, "content", "")
            text = content if isinstance(content, str) else str(content)
            match = re.search(r'read_messages\(chat_id="([^"]+)"\)', text)
            if match:
                return match.group(1)
        return None

    def _fill_missing_chat_target(self, args: dict[str, Any], request: Any) -> dict[str, Any]:
        if args.get("user_id"):
            return args
        if isinstance(args.get("chat_id"), str) and args["chat_id"].strip():
            return args
        notified_chat_id = self._latest_notified_chat_id(request)
        if notified_chat_id:
            return {**args, "chat_id": notified_chat_id}
        return args

    def _resolve_name(self, user_id: str) -> str:
        """Resolve display name from member_repo."""
        m = self._members.get_by_id(user_id) if self._members else None
        return m.name if m else "unknown"

    def _format_msgs(self, msgs: list, eid: str) -> str:
        lines = []
        for m in msgs:
            name = self._resolve_name(m.sender_id)
            tag = "you" if m.sender_id == eid else name
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
                msgs = msgs[: len(msgs) - skip_last] if len(msgs) > skip_last else []
            return msgs
        else:
            return self._messages.list_by_time_range(
                chat_id,
                after=parsed["after"],
                before=parsed["before"],
            )

    def _handle_list_chats(self, unread_only: bool = False, limit: int = 20) -> str:
        eid = self._user_id
        chats = self._chat_service.list_chats_for_user(eid)
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
                id_str = f" [user_id: {other_id}]" if other_id else ""
            lines.append(f"- {name}{id_str}{unread_str}{last_preview}")
        return "\n".join(lines)

    def _handle_read_messages(self, user_id: str | None = None, chat_id: str | None = None, range: str | None = None) -> str:
        eid = self._user_id
        if chat_id:
            pass  # use chat_id directly
        elif user_id:
            chat_id = self._chat_entities.find_chat_between(eid, user_id)
            if not chat_id:
                name = self._resolve_name(user_id)
                return f"No chat history with {name}."
        else:
            return "Provide user_id or chat_id."

        # @@@range-dispatch — if range is provided, use it regardless of unread state.
        if range:
            try:
                parsed = _parse_range(range)
            except ValueError as e:
                return str(e)
            msgs = self._fetch_by_range(chat_id, parsed)
            if not msgs:
                return "No messages in that range."
            # @@@range-marks-read — WORKAROUND: unblock send_message by pushing
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

    def _handle_send_message(
        self,
        content: str,
        user_id: str | None = None,
        chat_id: str | None = None,
        signal: str = "open",
        mentions: list[str] | None = None,
    ) -> str:
        eid = self._user_id
        # @@@read-before-write — resolve chat_id, then check unread
        resolved_chat_id = chat_id
        target_name = "chat"

        if chat_id:
            if not self._chat_entities.is_participant_in_chat(chat_id, eid):
                raise RuntimeError(f"You are not a member of chat {chat_id}")
        elif user_id:
            if user_id == eid:
                raise RuntimeError("Cannot send a message to yourself.")
            target_name = self._resolve_name(user_id)
            resolved_chat_id = self._chat_entities.find_chat_between(eid, user_id)
            if not resolved_chat_id:
                # New chat — no unread possible, create and send
                chat = self._chat_service.find_or_create_chat([eid, user_id])
                resolved_chat_id = chat.id
        else:
            raise RuntimeError("Provide user_id (for 1:1) or chat_id (for group)")

        # @@@read-before-write-gate — reject if unread messages exist
        unread = self._messages.count_unread(resolved_chat_id, eid)
        if unread > 0:
            raise RuntimeError(f"You have {unread} unread message(s). Call read_messages(chat_id='{resolved_chat_id}') first.")

        # Append signal to content (for read_messages) + pass through chain (for notification)
        effective_signal = signal if signal in ("yield", "close") else None
        if effective_signal:
            content = f"{content}\n[signal: {effective_signal}]"

        self._chat_service.send_message(resolved_chat_id, eid, content, mentions, signal=effective_signal)
        return f"Message sent to {target_name}."

    def _handle_search_messages(self, query: str, user_id: str | None = None) -> str:
        eid = self._user_id
        chat_id = None
        if user_id:
            chat_id = self._chat_entities.find_chat_between(eid, user_id)
        results = self._messages.search(query, chat_id=chat_id, limit=20)
        if not results:
            return f"No messages matching '{query}'."
        lines = []
        for m in results:
            name = self._resolve_name(m.sender_id)
            lines.append(f"[{name}] {m.content[:100]}")
        return "\n".join(lines)

    def _register_list_chats(self, registry: ToolRegistry) -> None:
        registry.register(
            ToolEntry(
                name="list_chats",
                mode=ToolMode.INLINE,
                schema=make_tool_schema(
                    name="list_chats",
                    description="List your chats. Returns chat summaries with user_ids of participants.",
                    properties={
                        "unread_only": {
                            "type": "boolean",
                            "description": "Only show chats with unread messages",
                            "default": False,
                        },
                        "limit": {"type": "integer", "description": "Max number of chats to return", "default": 20},
                    },
                ),
                handler=self._handle_list_chats,
                source="chat",
                is_read_only=True,
                is_concurrency_safe=True,
            )
        )

    def _register_read_messages(self, registry: ToolRegistry) -> None:
        registry.register(
            ToolEntry(
                name="read_messages",
                mode=ToolMode.INLINE,
                schema=make_tool_schema(
                    name="read_messages",
                    description=(
                        "Read chat messages. Returns unread messages by default.\n"
                        "If nothing unread, use range to read history:\n"
                        "  Negative index: '-10:-1' (last 10), '-5:' (last 5)\n"
                        "  Time interval: '-1h:', '-2d:-1d', '2026-03-20:2026-03-22'\n"
                        "Positive indices are NOT allowed."
                    ),
                    properties={
                        "user_id": {"type": "string", "description": "user_id for 1:1 chat history"},
                        "chat_id": {"type": "string", "description": "Chat_id for group chat history"},
                        "range": {
                            "type": "string",
                            "description": (
                                "History range. Negative index '-X:-Y' or time '-1h:', '2026-03-20:'. Positive indices NOT allowed."
                            ),
                        },
                    },
                    parameter_overrides={
                        "x-leon-required-any-of": [
                            ["user_id"],
                            ["chat_id"],
                        ],
                    },
                ),
                handler=self._handle_read_messages,
                source="chat",
                search_hint="read chat messages history conversation",
                is_read_only=True,
                is_concurrency_safe=True,
                validate_input=self._fill_missing_chat_target,
            )
        )

    def _register_send_message(self, registry: ToolRegistry) -> None:
        registry.register(
            ToolEntry(
                name="send_message",
                mode=ToolMode.INLINE,
                schema=make_tool_schema(
                    name="send_message",
                    description=(
                        "Send a message. Use user_id for 1:1 chats, chat_id for group chats.\n\n"
                        "You MUST call read_messages() first if you have unread messages — sending will fail otherwise.\n\n"
                        "Signal protocol — append to content:\n"
                        "  (no tag) = I expect a reply from you\n"
                        "  ::yield = I'm done with my turn; reply only if you want to\n"
                        "  ::close = conversation over, do NOT reply\n\n"
                        "For games/turns: do NOT append ::yield — just send the move and expect a reply."
                    ),
                    properties={
                        "content": {"type": "string", "description": "Message content"},
                        "user_id": {"type": "string", "description": "Target user_id (for 1:1 chat)"},
                        "chat_id": {"type": "string", "description": "Target chat_id (for group chat)"},
                        "signal": {
                            "type": "string",
                            "enum": ["open", "yield", "close"],
                            "description": "Signal intent to recipient",
                            "default": "open",
                        },
                        "mentions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "User IDs to @mention (overrides mute for these recipients)",
                        },
                    },
                    required=["content"],
                    parameter_overrides={
                        "x-leon-required-any-of": [
                            ["content", "user_id"],
                            ["content", "chat_id"],
                        ],
                    },
                ),
                handler=self._handle_send_message,
                source="chat",
                search_hint="send message reply chat entity",
                validate_input=self._fill_missing_chat_target,
            )
        )

    def _register_search_messages(self, registry: ToolRegistry) -> None:
        registry.register(
            ToolEntry(
                name="search_messages",
                mode=ToolMode.INLINE,
                schema=make_tool_schema(
                    name="search_messages",
                    description="Search messages. Optionally filter by user_id.",
                    properties={
                        "query": {"type": "string", "description": "Search query"},
                        "user_id": {
                            "type": "string",
                            "description": "Optional: only search in chat with this user",
                        },
                    },
                    required=["query"],
                ),
                handler=self._handle_search_messages,
                source="chat",
                search_hint="search messages query chat history",
                is_read_only=True,
                is_concurrency_safe=True,
            )
        )
