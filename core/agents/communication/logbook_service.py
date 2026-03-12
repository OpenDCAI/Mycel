"""Logbook Service — agent tools for checking messages, replying, and marking read.

Registered into ToolRegistry so the agent can communicate via conversations.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry
from storage.contracts import ConversationMessageRow
from storage.providers.sqlite.conversation_repo import (
    SQLiteConversationMemberRepo,
    SQLiteConversationMessageRepo,
    SQLiteConversationRepo,
)
from storage.providers.sqlite.member_repo import SQLiteMemberRepo

logger = logging.getLogger(__name__)


class LogbookService:
    """Registers logbook tools (check_messages, reply, mark_read) into ToolRegistry."""

    def __init__(
        self,
        registry: ToolRegistry,
        member_id: str,
        *,
        conversations: SQLiteConversationRepo | None = None,
        conv_members: SQLiteConversationMemberRepo | None = None,
        conv_messages: SQLiteConversationMessageRepo | None = None,
        members: SQLiteMemberRepo | None = None,
        event_bus: Any | None = None,
    ) -> None:
        self._member_id = member_id
        # @@@shared-repos - reuse existing repos to avoid "database is locked" from competing connections
        self._conversations = conversations or SQLiteConversationRepo()
        self._conv_members = conv_members or SQLiteConversationMemberRepo()
        self._conv_messages = conv_messages or SQLiteConversationMessageRepo()
        self._members = members or SQLiteMemberRepo()
        # @@@logbook-sse-push - duck-typed event bus with .publish(conv_id, event_dict) for real-time SSE
        self._event_bus = event_bus
        self._register(registry)

    def _register(self, registry: ToolRegistry) -> None:
        registry.register(ToolEntry(
            name="logbook_check_messages",
            mode=ToolMode.INLINE,
            schema={
                "name": "logbook_check_messages",
                "description": "Check your logbook for unread messages across all conversations. Returns messages grouped by conversation with sender names.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
            handler=self._check_messages,
            source="logbook",
        ))

        registry.register(ToolEntry(
            name="logbook_reply",
            mode=ToolMode.INLINE,
            schema={
                "name": "logbook_reply",
                "description": "Reply to a conversation in your logbook. The reply will be stored and visible to the other member.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conversation_id": {
                            "type": "string",
                            "description": "The conversation ID to reply to (from logbook_check_messages output)",
                        },
                        "content": {
                            "type": "string",
                            "description": "Your reply message content",
                        },
                    },
                    "required": ["conversation_id", "content"],
                },
            },
            handler=self._reply,
            source="logbook",
        ))

        registry.register(ToolEntry(
            name="logbook_mark_read",
            mode=ToolMode.INLINE,
            schema={
                "name": "logbook_mark_read",
                "description": "Mark all messages in a conversation as read up to now.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conversation_id": {
                            "type": "string",
                            "description": "The conversation ID to mark as read",
                        },
                    },
                    "required": ["conversation_id"],
                },
            },
            handler=self._mark_read,
            source="logbook",
        ))

    def _check_messages(self) -> str:
        """Check unread messages across all conversations."""
        conv_ids = self._conv_members.list_conversations_for_member(self._member_id)
        if not conv_ids:
            return "No conversations found."

        results = []
        for cid in conv_ids:
            unread_count = self._conv_messages.count_unread(cid, self._member_id)
            if unread_count == 0:
                continue

            conv = self._conversations.get_by_id(cid)
            title = conv.title if conv else "Unknown"

            # Get recent unread messages (last 10)
            all_msgs = self._conv_messages.list_by_conversation(cid, limit=10)
            # Filter to messages NOT from self
            unread = [m for m in all_msgs if m.sender_id != self._member_id][-unread_count:]

            msg_lines = []
            for m in unread:
                sender = self._members.get_by_id(m.sender_id)
                sender_name = sender.name if sender else m.sender_id[:8]
                msg_lines.append(f"  [{sender_name}]: {m.content}")

            results.append(
                f"Conversation: {title} (id: {cid})\n"
                f"Unread: {unread_count}\n"
                + "\n".join(msg_lines)
            )

        if not results:
            return "No unread messages."

        return "\n\n".join(results)

    def _reply(self, conversation_id: str, content: str) -> str:
        """Reply to a conversation."""
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

        # Mark as read up to now (we just wrote, so we've seen everything)
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

        return f"Reply sent (id: {msg_id})"

    def _mark_read(self, conversation_id: str) -> str:
        """Mark all messages in a conversation as read."""
        if not self._conv_members.is_member(conversation_id, self._member_id):
            return f"Error: you are not a member of conversation {conversation_id}"

        self._conv_members.update_last_read(conversation_id, self._member_id, time.time())
        return "Marked as read."
