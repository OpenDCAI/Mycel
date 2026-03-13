"""Conversation service — CRUD + message storage."""

from __future__ import annotations

import logging
import time
import uuid

from storage.contracts import ConversationMessageRow, ConversationRow

logger = logging.getLogger(__name__)


def _member_details(members_repo: any, member_ids: list[str]) -> list[dict]:
    """Build member_details list: [{id, name, type}] for each participant."""
    details = []
    for mid in member_ids:
        m = members_repo.get_by_id(mid)
        if m:
            details.append({"id": m.id, "name": m.name, "type": m.type.value})
    return details


class ConversationService:
    """Thin layer over conversation repos + message storage."""

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

    def create_member_conversation(self, member_ids: list[str], title: str | None = None) -> dict:
        """Create a conversation between any two members."""
        if len(member_ids) != 2:
            raise ValueError("Exactly 2 member IDs required")

        members = []
        for mid in member_ids:
            m = self._members.get_by_id(mid)
            if not m:
                raise ValueError(f"Member {mid} not found")
            members.append(m)

        now = time.time()
        conv_id = str(uuid.uuid4())
        conv_title = title or f"{members[0].name} ↔ {members[1].name}"

        self._conversations.create(ConversationRow(
            id=conv_id, title=conv_title, created_at=now,
        ))
        for mid in member_ids:
            self._conv_members.add_member(conv_id, mid, now)

        self._contacts.create_pair(member_ids[0], member_ids[1], now)

        return {
            "id": conv_id,
            "title": conv_title,
            "status": "active",
            "created_at": now,
            "members": member_ids,
            "member_details": _member_details(self._members, member_ids),
        }

    def archive_conversation(self, conversation_id: str) -> None:
        """Archive a conversation (soft delete)."""
        self._conversations.update_status(conversation_id, "archived")

    def list_for_member(self, member_id: str) -> list[dict]:
        """List conversations the member participates in."""
        conv_ids = self._conv_members.list_conversations_for_member(member_id)
        results = []
        for cid in conv_ids:
            conv = self._conversations.get_by_id(cid)
            if conv and conv.status != "archived":
                members = self._conv_members.list_members(cid)
                member_ids = [m.member_id for m in members]
                results.append({
                    "id": conv.id,
                    "title": conv.title,
                    "status": conv.status,
                    "created_at": conv.created_at,
                    "members": member_ids,
                    "member_details": _member_details(self._members, member_ids),
                })
        return results

    def get(self, conversation_id: str) -> dict | None:
        """Get a single conversation with member list."""
        conv = self._conversations.get_by_id(conversation_id)
        if not conv:
            return None
        members = self._conv_members.list_members(conversation_id)
        member_ids = [m.member_id for m in members]
        return {
            "id": conv.id,
            "title": conv.title,
            "status": conv.status,
            "created_at": conv.created_at,
            "members": member_ids,
            "member_details": _member_details(self._members, member_ids),
        }

    def is_member(self, conversation_id: str, member_id: str) -> bool:
        """Check if member participates in conversation."""
        return self._conv_members.is_member(conversation_id, member_id)

    def send_message(self, conversation_id: str, sender_id: str, content: str) -> dict:
        """Store a message and return it.

        Delivery to recipients is handled by DeliveryRouter in the caller (router layer).
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

        # @@@auto-contact - create contact pairs with all other members
        members = self._conv_members.list_members(conversation_id)
        for cm in members:
            if cm.member_id != sender_id:
                self._contacts.create_pair(sender_id, cm.member_id, now)

        return {
            "message": {
                "id": msg_id,
                "conversation_id": conversation_id,
                "sender_id": sender_id,
                "content": content,
                "created_at": now,
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
