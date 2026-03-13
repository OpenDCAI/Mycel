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

    def create_conversation(self, creator_id: str, agent_member_id: str, title: str | None = None) -> dict:
        """Create a new conversation between creator and agent.

        Returns existing active conversation if one already exists between these members.
        """
        agent = self._members.get_by_id(agent_member_id)
        if not agent:
            raise ValueError(f"Agent member {agent_member_id} not found")

        # @@@dedup-conversation - return existing if already exists
        existing = self._find_existing_conversation(creator_id, agent_member_id)
        if existing:
            return existing

        now = time.time()
        conv_id = str(uuid.uuid4())
        conv_title = title or f"Chat with {agent.name}"

        self._conversations.create(ConversationRow(
            id=conv_id, agent_member_id=agent_member_id,
            title=conv_title, created_at=now,
        ))
        self._conv_members.add_member(conv_id, creator_id, now)
        self._conv_members.add_member(conv_id, agent_member_id, now)

        # Auto-create contact pair if not exists
        self._contacts.create_pair(creator_id, agent_member_id, now)

        return {
            "id": conv_id,
            "agent_member_id": agent_member_id,
            "agent_name": agent.name,
            "title": conv_title,
            "status": "active",
            "created_at": now,
            "members": [creator_id, agent_member_id],
        }

    def _find_existing_conversation(self, member_a: str, member_b: str) -> dict | None:
        """Find an existing active conversation between two members."""
        a_convs = set(self._conv_members.list_conversations_for_member(member_a))
        b_convs = set(self._conv_members.list_conversations_for_member(member_b))
        shared = a_convs & b_convs
        for cid in shared:
            conv = self._conversations.get_by_id(cid)
            if conv and conv.status == "active":
                members = self._conv_members.list_members(cid)
                agent = self._members.get_by_id(conv.agent_member_id)
                return {
                    "id": conv.id,
                    "agent_member_id": conv.agent_member_id,
                    "agent_name": agent.name if agent else "Leon",
                    "title": conv.title,
                    "status": conv.status,
                    "created_at": conv.created_at,
                    "members": [m.member_id for m in members],
                }
        return None

    # @@@member-conversation - create conversation between any two members (not just human+agent)
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

        # Use first agent member as agent_member_id hint (for frontend brain SSE)
        from storage.contracts import MemberType
        agent_hint = next((m.id for m in members if m.type == MemberType.MYCEL_AGENT), member_ids[0])

        self._conversations.create(ConversationRow(
            id=conv_id, agent_member_id=agent_hint,
            title=conv_title, created_at=now,
        ))
        for mid in member_ids:
            self._conv_members.add_member(conv_id, mid, now)

        self._contacts.create_pair(member_ids[0], member_ids[1], now)

        return {
            "id": conv_id,
            "agent_member_id": agent_hint,
            "title": conv_title,
            "status": "active",
            "created_at": now,
            "members": member_ids,
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
                agent = self._members.get_by_id(conv.agent_member_id)
                results.append({
                    "id": conv.id,
                    "agent_member_id": conv.agent_member_id,
                    "agent_name": agent.name if agent else "Leon",
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
        agent = self._members.get_by_id(conv.agent_member_id)
        return {
            "id": conv.id,
            "agent_member_id": conv.agent_member_id,
            "agent_name": agent.name if agent else "Leon",
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
