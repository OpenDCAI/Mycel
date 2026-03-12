"""Conversation service — CRUD + message routing to agent brain."""

from __future__ import annotations

import logging
import time
import uuid

from storage.contracts import ConversationMessageRow, ConversationRow

logger = logging.getLogger(__name__)


class ConversationService:
    """Thin layer over conversation repos + message routing."""

    def __init__(
        self,
        conversations: any,
        conv_members: any,
        conv_messages: any,
        contacts: any,
        members: any,
    ) -> None:
        self._conversations = conversations
        self._conv_members = conv_members
        self._conv_messages = conv_messages
        self._contacts = contacts
        self._members = members

    def list_for_member(self, member_id: str) -> list[dict]:
        """List conversations the member participates in."""
        conv_ids = self._conv_members.list_conversations_for_member(member_id)
        results = []
        for cid in conv_ids:
            conv = self._conversations.get_by_id(cid)
            if conv:
                members = self._conv_members.list_members(cid)
                results.append({
                    "id": conv.id,
                    "agent_member_id": conv.agent_member_id,
                    "title": conv.title,
                    "status": conv.status,
                    "created_at": conv.created_at,
                    "members": [m.member_id for m in members],
                })
        return results

    def get(self, conversation_id: str) -> dict | None:
        """Get a single conversation with member list."""
        conv = self._conversations.get_by_id(conversation_id)
        if not conv:
            return None
        members = self._conv_members.list_members(conversation_id)
        return {
            "id": conv.id,
            "agent_member_id": conv.agent_member_id,
            "title": conv.title,
            "status": conv.status,
            "created_at": conv.created_at,
            "members": [m.member_id for m in members],
        }

    def is_member(self, conversation_id: str, member_id: str) -> bool:
        """Check if member participates in conversation."""
        return self._conv_members.is_member(conversation_id, member_id)

    def send_message(self, conversation_id: str, sender_id: str, content: str) -> dict:
        """Store a message and return it + routing info for the caller to enqueue.

        Does NOT enqueue to the agent brain — caller handles routing.
        This keeps the service free of async/app dependencies.
        """
        conv = self._conversations.get_by_id(conversation_id)
        if not conv:
            raise ValueError(f"Conversation {conversation_id} not found")

        if not self._conv_members.is_member(conversation_id, sender_id):
            raise PermissionError(f"Member {sender_id} is not in conversation {conversation_id}")

        now = time.time()
        msg_id = str(uuid.uuid4())
        self._conv_messages.create(ConversationMessageRow(
            id=msg_id,
            conversation_id=conversation_id,
            sender_id=sender_id,
            content=content,
            created_at=now,
        ))

        # @@@auto-contact - create contact pair on first message if not exists
        self._contacts.create_pair(sender_id, conv.agent_member_id, now)

        sender = self._members.get_by_id(sender_id)
        sender_name = sender.name if sender else "unknown"

        return {
            "message": {
                "id": msg_id,
                "conversation_id": conversation_id,
                "sender_id": sender_id,
                "content": content,
                "created_at": now,
            },
            "routing": {
                "agent_member_id": conv.agent_member_id,
                "brain_thread_id": f"brain-{conv.agent_member_id}",
                "sender_name": sender_name,
                "conversation_id": conversation_id,
            },
        }

    def list_messages(self, conversation_id: str, limit: int = 50, before: float | None = None) -> list[dict]:
        """List messages in a conversation, newest last."""
        rows = self._conv_messages.list_by_conversation(conversation_id, limit=limit, before=before)
        return [
            {
                "id": r.id,
                "conversation_id": r.conversation_id,
                "sender_id": r.sender_id,
                "content": r.content,
                "created_at": r.created_at,
            }
            for r in rows
        ]
