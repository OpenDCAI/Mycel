"""Chat tool service (messaging module version).

Provides 4 tools: list_chats, read_messages, send_message, search_messages.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry
from core.runtime.tool_result import tool_error

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
    """Registers 4 chat tools into ToolRegistry (messaging module version)."""

    def __init__(
        self,
        registry: ToolRegistry,
        owner_id: str,
        *,
        chat_identity_id: str | None = None,
        user_id: str | None = None,
        messaging_service: Any = None,  # MessagingService (new)
        chat_member_repo: Any = None,  # SupabaseChatMemberRepo
        messages_repo: Any = None,  # SupabaseMessagesRepo
        user_repo: Any = None,
        thread_repo: Any = None,
        relationship_repo: Any = None,
    ) -> None:
        identity_id = chat_identity_id or user_id
        if not identity_id:
            raise ValueError("ChatToolService requires chat_identity_id or legacy user_id")
        self._chat_identity_id: str = identity_id
        self._owner_id = owner_id
        self._messaging = messaging_service
        self._user_repo = user_repo
        self._thread_repo = thread_repo
        self._relationships = relationship_repo
        self._register(registry)

    def _resolve_display_user(self, social_user_id: str) -> Any | None:
        user = self._user_repo.get_by_id(social_user_id) if self._user_repo else None
        if user is not None:
            return user
        if self._thread_repo is None:
            return None
        thread = self._thread_repo.get_by_user_id(social_user_id)
        if thread is None:
            return None
        agent_user_id = thread.get("agent_user_id")
        if not agent_user_id or self._user_repo is None:
            return None
        return self._user_repo.get_by_id(agent_user_id)

    def _register(self, registry: ToolRegistry) -> None:
        self._register_list_chats(registry)
        self._register_chat_read(registry)
        self._register_chat_send(registry)
        self._register_search_messages(registry)

    def _format_msgs(self, msgs: list[dict], eid: str) -> str:
        lines = []
        for m in msgs:
            sender = self._resolve_display_user(m.get("sender_id", ""))
            name = sender.display_name if sender else "unknown"
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
            msgs = self._messaging.list_messages(chat_id, limit=fetch_count, viewer_id=self._chat_identity_id)
            if skip_last > 0:
                msgs = msgs[: len(msgs) - skip_last] if len(msgs) > skip_last else []
            return msgs
        else:
            after_iso = datetime.fromtimestamp(parsed["after"], tz=UTC).isoformat() if parsed.get("after") else None
            before_iso = datetime.fromtimestamp(parsed["before"], tz=UTC).isoformat() if parsed.get("before") else None
            return self._messaging.list_messages_by_time_range(chat_id, after=after_iso, before=before_iso)

    def _register_list_chats(self, registry: ToolRegistry) -> None:
        eid = self._chat_identity_id

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
                name="list_chats",
                mode=ToolMode.INLINE,
                schema={
                    "name": "list_chats",
                    "description": "List your chats. Returns chat summaries with participant ids from the current social-id slot.",
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
        eid = self._chat_identity_id

        def handle(user_id: str | None = None, chat_id: str | None = None, range: str | None = None) -> str:
            if chat_id:
                pass
            elif user_id:
                chat_id = self._messaging.find_direct_chat_id(eid, user_id)
                if not chat_id:
                    target = self._resolve_display_user(user_id)
                    name = target.display_name if target else user_id
                    return f"No chat history with {name}."
            else:
                return "Provide user_id or chat_id."

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
                name="read_messages",
                mode=ToolMode.INLINE,
                schema={
                    "name": "read_messages",
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
                            "user_id": {
                                "type": "string",
                                "minLength": 1,
                                "description": "Participant id for 1:1 chat history. Parameter name is legacy.",
                            },
                            "chat_id": {
                                "type": "string",
                                "minLength": 1,
                                "description": "Chat_id for group chat history",
                            },
                            "range": {
                                "type": "string",
                                "description": "History range. Negative index '-X:-Y' or time '-1h:', '2026-03-20:'.",
                            },
                        },
                        "x-leon-required-any-of": [["user_id"], ["chat_id"]],
                    },
                },
                handler=handle,
                source="chat",
            )
        )

    def _register_chat_send(self, registry: ToolRegistry) -> None:
        eid = self._chat_identity_id

        def handle(
            content: str,
            user_id: str | None = None,
            chat_id: str | None = None,
            signal: str = "open",
            mentions: list[str] | None = None,
        ) -> str:
            resolved_chat_id = chat_id
            target_name = "chat"

            if chat_id:
                if not self._messaging.is_chat_member(chat_id, eid):
                    raise RuntimeError(f"You are not a member of chat {chat_id}")
            elif user_id:
                if user_id == eid:
                    raise RuntimeError("Cannot send a message to yourself.")
                target = self._resolve_display_user(user_id)
                if not target:
                    raise RuntimeError(f"User not found: {user_id}")
                target_name = target.display_name
                chat = self._messaging.find_or_create_chat([eid, user_id])
                resolved_chat_id = chat["id"]
            else:
                raise RuntimeError("Provide user_id (for 1:1) or chat_id (for group)")

            # @@@read-before-send-gate - group chats and direct chats share the same
            # delivery invariant: you must consume unread messages before replying,
            # otherwise siblings can race on stale history and fork the conversation.
            unread = self._messaging.count_unread(resolved_chat_id, eid)
            if unread > 0:
                return tool_error(
                    f"You have {unread} unread message(s). Call read_messages(chat_id='{resolved_chat_id}') first.",
                    metadata={"error_type": "chat_not_caught_up", "chat_id": resolved_chat_id},
                )

            effective_signal = signal if signal in ("yield", "close") else None
            if effective_signal:
                content = f"{content}\n[signal: {effective_signal}]"

            try:
                self._messaging.send(
                    resolved_chat_id,
                    eid,
                    content,
                    mentions=mentions,
                    signal=effective_signal,
                    enforce_caught_up=True,
                )
            except RuntimeError as exc:
                message = str(exc)
                if message.startswith("Chat advanced after your last read."):
                    return tool_error(
                        message,
                        metadata={"error_type": "chat_not_caught_up", "chat_id": resolved_chat_id},
                    )
                raise
            return f"Message sent to {target_name}."

        registry.register(
            ToolEntry(
                name="send_message",
                mode=ToolMode.INLINE,
                schema={
                    "name": "send_message",
                    "description": (
                        "Send a message. Use user_id for 1:1 chats and chat_id for group chats.\n"
                        "The user_id parameter name is legacy.\n\n"
                        "For any chat, you MUST call read_messages() first if you have unread messages.\n"
                        "Sending will fail otherwise.\n\n"
                        "Signal protocol:\n"
                        "  (no tag) = I expect a reply from you\n"
                        "  ::yield = I'm done with my turn; reply only if you want to\n"
                        "  ::close = conversation over, do NOT reply"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "minLength": 1, "description": "Message content"},
                            "user_id": {
                                "type": "string",
                                "minLength": 1,
                                "description": ("Target participant id for 1:1 chat. Parameter name is legacy."),
                            },
                            "chat_id": {
                                "type": "string",
                                "minLength": 1,
                                "description": "Target chat_id (for group chat)",
                            },
                            "signal": {"type": "string", "enum": ["open", "yield", "close"], "default": "open"},
                            "mentions": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "User IDs to @mention",
                            },
                        },
                        "required": ["content"],
                        "x-leon-required-any-of": [["user_id"], ["chat_id"]],
                    },
                },
                handler=handle,
                source="chat",
            )
        )

    def _register_search_messages(self, registry: ToolRegistry) -> None:
        eid = self._chat_identity_id

        def handle(query: str, user_id: str | None = None) -> str:
            chat_id = None
            if user_id:
                chat_id = self._messaging.find_direct_chat_id(eid, user_id)
                if not chat_id:
                    target = self._resolve_display_user(user_id)
                    name = target.display_name if target else user_id
                    return f"No messages matching '{query}' with {name}."
            results = self._messaging.search_messages(query, chat_id=chat_id)
            if not results:
                return f"No messages matching '{query}'."
            lines = []
            for m in results:
                sender = self._resolve_display_user(m.get("sender_id", ""))
                name = sender.display_name if sender else "unknown"
                lines.append(f"[{name}] {m.get('content', '')[:100]}")
            return "\n".join(lines)

        registry.register(
            ToolEntry(
                name="search_messages",
                mode=ToolMode.INLINE,
                schema={
                    "name": "search_messages",
                    "description": "Search messages. Optionally filter by user_id.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "minLength": 1, "description": "Search query"},
                            "user_id": {
                                "type": "string",
                                "minLength": 1,
                                "description": "Optional: only search in chat with this participant id. Parameter name is legacy.",
                            },
                        },
                        "required": ["query"],
                    },
                },
                handler=handle,
                source="chat",
            )
        )
