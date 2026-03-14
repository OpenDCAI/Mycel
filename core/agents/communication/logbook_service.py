"""Logbook Service v3 — 2 tools: logbook (read) + logbook_reply (send).

Replaces the v2 trio (check_messages/reply/mark_read) with a unified read tool
that supports contact overview, message history, search, and pagination.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from core.agents.communication.directory_service import DirectoryService
from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry
from storage.contracts import ConversationMessageRow, MemberRow
from storage.providers.sqlite.contact_repo import SQLiteContactRepo
from storage.providers.sqlite.conversation_repo import (
    SQLiteConversationMemberRepo,
    SQLiteConversationMessageRepo,
    SQLiteConversationRepo,
)
from storage.providers.sqlite.member_repo import SQLiteMemberRepo

logger = logging.getLogger(__name__)


class LogbookService:
    """Registers logbook/logbook_reply tools into ToolRegistry."""

    def __init__(
        self,
        registry: ToolRegistry,
        member_id: str,
        *,
        conversations: SQLiteConversationRepo | None = None,
        conv_members: SQLiteConversationMemberRepo | None = None,
        conv_messages: SQLiteConversationMessageRepo | None = None,
        members: SQLiteMemberRepo | None = None,
        contacts: SQLiteContactRepo | None = None,
        event_bus: Any | None = None,
        message_router: Any | None = None,
    ) -> None:
        self._member_id = member_id
        # @@@shared-repos - reuse existing repos to avoid "database is locked" from competing connections
        self._conversations = conversations or SQLiteConversationRepo()
        self._conv_members = conv_members or SQLiteConversationMemberRepo()
        self._conv_messages = conv_messages or SQLiteConversationMessageRepo()
        self._members = members or SQLiteMemberRepo()
        self._contacts = contacts or SQLiteContactRepo()
        # @@@logbook-sse-push - duck-typed event bus with .publish(conv_id, event_dict) for real-time SSE
        self._event_bus = event_bus
        # @@@logbook-delivery - callback(conv_id, sender_id, content) routes to agent recipients' brains
        self._message_router = message_router
        # @@@logbook-directory - shared discovery service for browse/search
        self._directory = DirectoryService(self._members, self._contacts)
        self._register(registry)

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def _register(self, registry: ToolRegistry) -> None:
        registry.register(ToolEntry(
            name="logbook",
            mode=ToolMode.INLINE,
            schema={
                "name": "logbook",
                "description": (
                    "Read your logbook. No args = contact overview with unread counts. "
                    "Pass conversation_id to read messages. Pass query to search within a conversation. "
                    "Pass member to filter contacts by name. "
                    "Pass directory=true to browse the member directory and discover contacts and strangers.\n\n"
                    "Signal tags at the end of messages:\n"
                    "  (no tag) — expecting a reply\n"
                    "  ::yield — I have nothing more to add; whether to continue is up to you\n"
                    "  ::close — conversation over, do NOT reply"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directory": {
                            "type": "boolean",
                            "description": "Browse the member directory to discover contacts and strangers",
                        },
                        "search": {
                            "type": "string",
                            "description": "Search members by name (used with directory=true)",
                        },
                        "type_filter": {
                            "type": "string",
                            "description": "Filter by member type: human, mycel_agent, openclaw_agent (used with directory=true)",
                        },
                        "member": {
                            "type": "string",
                            "description": "Contact name or UUID — fuzzy match",
                        },
                        "conversation_id": {
                            "type": "string",
                            "description": "Read messages from this conversation",
                        },
                        "query": {
                            "type": "string",
                            "description": "Keyword search (requires conversation_id)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Page size (default: 50 contacts / 100 messages)",
                        },
                        "before": {
                            "type": "number",
                            "description": "Timestamp ceiling for pagination",
                        },
                    },
                },
            },
            handler=self._logbook,
            source="logbook",
        ))

        registry.register(ToolEntry(
            name="logbook_reply",
            mode=ToolMode.INLINE,
            schema={
                "name": "logbook_reply",
                "description": (
                    "Send a message. Use conversation_id for existing conversations. "
                    "Use 'to' (member name or id) to message someone new — "
                    "a conversation will be created automatically if needed.\n\n"
                    "No tag = expecting reply. "
                    "::yield = I have nothing more to add, up to you. "
                    "::close = I want to end this conversation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conversation_id": {
                            "type": "string",
                            "description": "The conversation to reply to (use this OR 'to', not both)",
                        },
                        "to": {
                            "type": "string",
                            "description": "Member name or id to message — auto-creates conversation if needed",
                        },
                        "content": {
                            "type": "string",
                            "description": "Your message",
                        },
                    },
                    "required": ["content"],
                },
            },
            handler=self._reply,
            source="logbook",
        ))

    # ------------------------------------------------------------------
    # logbook — unified read tool
    # ------------------------------------------------------------------

    def _logbook(
        self,
        directory: bool | None = None,
        search: str | None = None,
        type_filter: str | None = None,
        member: str | None = None,
        conversation_id: str | None = None,
        query: str | None = None,
        limit: int | None = None,
        before: float | None = None,
    ) -> str:
        # @@@logbook-dispatch - four modes: directory, search, message list, contact tree
        if directory:
            return self._handle_directory(search, type_filter)
        if conversation_id:
            if query:
                return self._handle_search(conversation_id, query, limit or 50)
            return self._handle_messages(conversation_id, limit or 100, before)
        return self._handle_contact_tree(member, limit or 50)

    # ------------------------------------------------------------------
    # Mode 1: Search within a conversation
    # ------------------------------------------------------------------

    def _handle_search(self, conversation_id: str, query: str, limit: int) -> str:
        conv = self._conversations.get_by_id(conversation_id)
        if not conv:
            return f"Error: conversation {conversation_id} not found"

        contact_name = self._find_contact_name(conversation_id)
        matches = self._conv_messages.search_in_conversation(conversation_id, query, limit=limit)
        return self._format_search(conv.title or "Untitled", contact_name, conversation_id, query, matches)

    # ------------------------------------------------------------------
    # Mode 2: Message list for a conversation
    # ------------------------------------------------------------------

    def _handle_messages(self, conversation_id: str, limit: int, before: float | None) -> str:
        conv = self._conversations.get_by_id(conversation_id)
        if not conv:
            return f"Error: conversation {conversation_id} not found"

        contact_name = self._find_contact_name(conversation_id)
        messages = self._conv_messages.list_by_conversation(conversation_id, limit=limit, before=before)
        last_read_at = self._conv_members.get_last_read_at(conversation_id, self._member_id)
        unread_count = self._conv_messages.count_unread(conversation_id, self._member_id)

        return self._format_messages(
            conv.title or "Untitled", contact_name, conversation_id,
            messages, last_read_at, unread_count,
        )

    # ------------------------------------------------------------------
    # Mode 3: Contact overview tree
    # ------------------------------------------------------------------

    def _handle_contact_tree(self, member_filter: str | None, limit: int) -> str:
        conv_ids = self._conv_members.list_conversations_for_member(self._member_id)
        if not conv_ids:
            return "No conversations yet."

        # Resolve member filter
        target_member: MemberRow | None = None
        if member_filter:
            target_member = self._resolve_member(member_filter)
            if not target_member:
                return f"No contact matching \"{member_filter}\" found."

        # Build per-contact data: {contact_member_id: [(conv, unread, last_msg, last_ts)]}
        contacts: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for cid in conv_ids:
            conv = self._conversations.get_by_id(cid)
            if not conv:
                continue

            # Find the other member (contact)
            contact_id = self._find_contact_id(cid)
            if not contact_id:
                continue

            # Apply member filter
            if target_member and contact_id != target_member.id:
                continue

            unread = self._conv_messages.count_unread(cid, self._member_id)
            last_msgs = self._conv_messages.list_by_conversation(cid, limit=1)
            last_msg = last_msgs[-1] if last_msgs else None
            last_ts = last_msg.created_at if last_msg else conv.created_at

            contacts[contact_id].append({
                "conv": conv,
                "unread": unread,
                "last_msg": last_msg,
                "last_ts": last_ts,
            })

        if not contacts:
            if member_filter:
                return f"No conversations with \"{member_filter}\"."
            return "No conversations yet."

        # Sort contacts by most recent activity
        sorted_contacts = sorted(
            contacts.items(),
            key=lambda kv: max(d["last_ts"] for d in kv[1]),
            reverse=True,
        )

        # Compute cursor for pagination
        cursor = sorted_contacts[-1][1][-1]["last_ts"] if sorted_contacts else None

        return self._format_contact_tree(sorted_contacts[:limit], cursor)

    # ------------------------------------------------------------------
    # Mode 4: Directory — member discovery
    # ------------------------------------------------------------------

    def _handle_directory(self, search: str | None, type_filter: str | None) -> str:
        result = self._directory.browse(self._member_id, type_filter=type_filter, search=search)
        return self._format_directory(result, search)

    # ------------------------------------------------------------------
    # logbook_reply — send + mark read
    # ------------------------------------------------------------------

    def _reply(self, content: str, conversation_id: str | None = None, to: str | None = None) -> str:
        # @@@logbook-initiate - resolve 'to' param into a conversation, creating if needed
        if to and not conversation_id:
            conversation_id = self._resolve_or_create_conversation(to)
            if conversation_id is None:
                return f"Error: could not find member '{to}'"

        if not conversation_id:
            return "Error: provide either conversation_id or 'to' parameter"

        if not self._conv_members.is_member(conversation_id, self._member_id):
            return f"Error: you are not a member of conversation {conversation_id}"

        now = time.time()
        msg_id = str(uuid.uuid4())
        self._conv_messages.create(ConversationMessageRow(
            id=msg_id,
            conversation_id=conversation_id,
            sender_id=self._member_id,
            content=content,
            created_at=now,
        ))

        # Mark as read up to now
        self._conv_members.update_last_read(conversation_id, self._member_id, now)

        logger.info("Logbook reply: member=%s conv=%s msg=%s", self._member_id[:8], conversation_id[:8], msg_id[:8])

        if self._event_bus:
            self._event_bus.publish(conversation_id, {
                "event": "message",
                "id": msg_id,
                "sender_id": self._member_id,
                "content": content,
                "created_at": now,
            })

        # @@@logbook-delivery - route message to agent recipients in the conversation
        if self._message_router:
            try:
                self._message_router(conversation_id, self._member_id, content)
            except Exception:
                logger.exception("Message routing failed for conv=%s", conversation_id[:8])

        return f"Reply sent (id: {msg_id})"

    # ------------------------------------------------------------------
    # Member resolution — fuzzy match by name or UUID
    # ------------------------------------------------------------------

    def _resolve_member(self, member_str: str) -> MemberRow | None:
        # 1. UUID match
        m = self._members.get_by_id(member_str)
        if m:
            return m
        # 2. Exact name
        m = self._members.get_by_name(member_str)
        if m:
            return m
        # 3. Case-insensitive substring
        needle = member_str.lower()
        for m in self._members.list_all():
            if needle in m.name.lower():
                return m
        return None

    # ------------------------------------------------------------------
    # Conversation creation (for 'to' parameter in logbook_reply)
    # ------------------------------------------------------------------

    def _resolve_or_create_conversation(self, to: str) -> str | None:
        """Find or create a conversation with the target member.

        Returns conversation_id or None if member not found.
        """
        target = self._resolve_member(to)
        if not target:
            return None

        # Check if we already share a conversation
        my_convs = set(self._conv_members.list_conversations_for_member(self._member_id))
        their_convs = set(self._conv_members.list_conversations_for_member(target.id))
        shared = my_convs & their_convs
        for cid in shared:
            conv = self._conversations.get_by_id(cid)
            if conv and conv.status == "active":
                return cid

        # Create new conversation
        now = time.time()
        conv_id = str(uuid.uuid4())
        from storage.contracts import ConversationRow
        my_member = self._members.get_by_id(self._member_id)
        my_name = my_member.name if my_member else "Agent"
        title = f"{my_name} ↔ {target.name}"

        self._conversations.create(ConversationRow(
            id=conv_id, title=title, created_at=now,
        ))
        self._conv_members.add_member(conv_id, self._member_id, now)
        self._conv_members.add_member(conv_id, target.id, now)
        self._contacts.create_pair(self._member_id, target.id, now)

        logger.info("Logbook created conversation: %s ↔ %s (conv=%s)", self._member_id[:8], target.id[:8], conv_id[:8])
        return conv_id

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_contact_id(self, conversation_id: str) -> str | None:
        """Find the 'other' member in a conversation (not self)."""
        members = self._conv_members.list_members(conversation_id)
        for m in members:
            if m.member_id != self._member_id:
                return m.member_id
        return None

    def _find_contact_name(self, conversation_id: str) -> str:
        contact_id = self._find_contact_id(conversation_id)
        if not contact_id:
            return "Unknown"
        member = self._members.get_by_id(contact_id)
        return member.name if member else contact_id[:8]

    def _ts_label(self, ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%m-%d %H:%M")

    def _sender_name(self, sender_id: str) -> str:
        if sender_id == self._member_id:
            return "You"
        member = self._members.get_by_id(sender_id)
        return member.name if member else sender_id[:8]

    # ------------------------------------------------------------------
    # Output formatters
    # ------------------------------------------------------------------

    def _format_contact_tree(
        self,
        sorted_contacts: list[tuple[str, list[dict[str, Any]]]],
        cursor: float | None,
    ) -> str:
        lines = ["📖 Logbook", ""]
        total_unread = sum(d["unread"] for _, convs in sorted_contacts for d in convs)
        if total_unread:
            lines.append(f"  {total_unread} unread total")
            lines.append("")

        for contact_id, convs in sorted_contacts:
            member = self._members.get_by_id(contact_id)
            name = member.name if member else contact_id[:8]
            contact_unread = sum(d["unread"] for d in convs)
            unread_tag = f" ({contact_unread} unread)" if contact_unread else ""
            lines.append(f"  {name}{unread_tag}")

            for d in sorted(convs, key=lambda x: x["last_ts"], reverse=True):
                conv = d["conv"]
                u = d["unread"]
                last = d["last_msg"]
                unread_dot = "● " if u > 0 else "  "
                title = conv.title or "Untitled"
                preview = ""
                if last:
                    sender = self._sender_name(last.sender_id)
                    text = last.content[:60] + ("..." if len(last.content) > 60 else "")
                    preview = f" — {sender}: {text}"
                lines.append(f"    {unread_dot}{title} [id:{conv.id}]{preview}")

            lines.append("")

        if cursor:
            lines.append(f"  (before={cursor:.3f} for more)")

        return "\n".join(lines)

    def _format_messages(
        self,
        conv_title: str,
        contact_name: str,
        conv_id: str,
        messages: list[ConversationMessageRow],
        last_read_at: float | None,
        unread_count: int,
    ) -> str:
        lines = [f"📖 {conv_title}  (with {contact_name})", ""]

        separator_placed = False
        for msg in messages:
            # Place unread separator before the first unread message
            if not separator_placed and unread_count > 0 and last_read_at is not None:
                if msg.sender_id != self._member_id and msg.created_at > last_read_at:
                    lines.append(f"  ─── {unread_count} unread ───")
                    separator_placed = True

            sender = self._sender_name(msg.sender_id)
            ts = self._ts_label(msg.created_at)
            lines.append(f"  [{ts}] {sender}: {msg.content}")

        # If never-read and there are unread messages, place separator at the top
        if not separator_placed and unread_count > 0 and last_read_at is None:
            lines.insert(2, f"  ─── {unread_count} unread ───")

        lines.append("")
        if messages:
            lines.append(f"  (before={messages[0].created_at:.3f} for older)")
        lines.append(f"  conversation_id: {conv_id}")

        return "\n".join(lines)

    def _format_search(
        self,
        conv_title: str,
        contact_name: str,
        conv_id: str,
        query: str,
        matches: list[ConversationMessageRow],
    ) -> str:
        lines = [f"🔍 Search \"{query}\" in {conv_title} (with {contact_name})", ""]

        if not matches:
            lines.append("  No results.")
        else:
            lines.append(f"  {len(matches)} match(es):")
            lines.append("")
            for msg in matches:
                sender = self._sender_name(msg.sender_id)
                ts = self._ts_label(msg.created_at)
                lines.append(f"  [{ts}] {sender}: {msg.content}")

        lines.append("")
        lines.append(f"  conversation_id: {conv_id}")

        return "\n".join(lines)

    def _format_directory(self, result: Any, search: str | None) -> str:
        from core.agents.communication.directory_service import DirectoryResult

        r: DirectoryResult = result
        header = f"🔍 Directory search: \"{search}\"" if search else "📖 Directory"
        lines = [header, ""]

        def _entry_line(e: Any) -> str:
            label = e.name
            if e.owner:
                label += f" (owner: {e.owner['name']})"
            type_tag = f" [{e.type}]"
            desc = f" — {e.description}" if e.description else ""
            return f"    {label}{type_tag}{desc}  id:{e.id}"

        if r.contacts:
            lines.append(f"  Contacts ({len(r.contacts)}):")
            for e in r.contacts:
                lines.append(_entry_line(e))
            lines.append("")

        if r.others:
            lines.append(f"  Others ({len(r.others)}):")
            for e in r.others:
                lines.append(_entry_line(e))
            lines.append("")

        if not r.contacts and not r.others:
            lines.append("  No members found.")

        return "\n".join(lines)
