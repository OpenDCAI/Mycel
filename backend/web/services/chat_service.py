"""Chat service — entity-to-entity communication."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Callable

from storage.contracts import (
    ChatEntityRepo,
    ChatMessageRepo,
    ChatMessageRow,
    ChatRepo,
    ChatRow,
    DeliveryResolver,
    EntityRepo,
    MemberRepo,
)

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        chat_repo: ChatRepo,
        chat_entity_repo: ChatEntityRepo,
        chat_message_repo: ChatMessageRepo,
        entity_repo: EntityRepo,
        member_repo: MemberRepo,
        event_bus: Any = None,
        delivery_fn: Callable | None = None,
        delivery_resolver: DeliveryResolver | None = None,
    ) -> None:
        self._chats = chat_repo
        self._chat_entities = chat_entity_repo
        self._messages = chat_message_repo
        self._entities = entity_repo
        self._members = member_repo
        self._event_bus = event_bus
        self._delivery_fn = delivery_fn
        self._delivery_resolver = delivery_resolver

    def find_or_create_chat(self, entity_ids: list[str], title: str | None = None) -> ChatRow:
        """Find existing 1:1 chat between two entities, or create one."""
        if len(entity_ids) != 2:
            raise ValueError("Use create_group_chat() for 3+ entities")

        self._check_owner_agent_rule(entity_ids)

        existing_id = self._chat_entities.find_chat_between(entity_ids[0], entity_ids[1])
        if existing_id:
            return self._chats.get_by_id(existing_id)

        now = time.time()
        chat_id = str(uuid.uuid4())
        self._chats.create(ChatRow(id=chat_id, title=title, created_at=now))
        for eid in entity_ids:
            self._chat_entities.add_entity(chat_id, eid, now)
        return self._chats.get_by_id(chat_id)

    def create_group_chat(self, entity_ids: list[str], title: str | None = None) -> ChatRow:
        """Create a group chat with 3+ entities."""
        if len(entity_ids) < 3:
            raise ValueError("Group chat requires 3+ entities")
        now = time.time()
        chat_id = str(uuid.uuid4())
        self._chats.create(ChatRow(id=chat_id, title=title, created_at=now))
        for eid in entity_ids:
            self._chat_entities.add_entity(chat_id, eid, now)
        return self._chats.get_by_id(chat_id)

    def send_message(
        self, chat_id: str, sender_entity_id: str, content: str,
        mentioned_entity_ids: list[str] | None = None,
    ) -> ChatMessageRow:
        """Send a message in a chat."""
        logger.debug("[send_message] chat=%s sender=%s content=%.50s", chat_id[:8], sender_entity_id[:15], content[:50])
        mentions = mentioned_entity_ids or []
        now = time.time()
        msg_id = str(uuid.uuid4())
        msg = ChatMessageRow(
            id=msg_id, chat_id=chat_id, sender_entity_id=sender_entity_id,
            content=content, mentioned_entity_ids=mentions, created_at=now,
        )
        self._messages.create(msg)

        sender = self._entities.get_by_id(sender_entity_id)
        sender_name = sender.name if sender else "unknown"

        if self._event_bus:
            self._event_bus.publish(chat_id, {
                "event": "message",
                "data": {
                    "id": msg_id,
                    "chat_id": chat_id,
                    "sender_entity_id": sender_entity_id,
                    "sender_name": sender_name,
                    "content": content,
                    "mentioned_entity_ids": mentions,
                    "created_at": now,
                },
            })

        self._deliver_to_agents(chat_id, sender_entity_id, content, mentions)
        return msg

    def _deliver_to_agents(
        self, chat_id: str, sender_entity_id: str, content: str,
        mentioned_entity_ids: list[str] | None = None,
    ) -> None:
        """For each non-sender agent entity in the chat, deliver to their brain thread."""
        mentions = set(mentioned_entity_ids or [])
        participants = self._chat_entities.list_entities(chat_id)
        sender_entity = self._entities.get_by_id(sender_entity_id)
        sender_name = sender_entity.name if sender_entity else "unknown"

        for ce in participants:
            if ce.entity_id == sender_entity_id:
                continue
            entity = self._entities.get_by_id(ce.entity_id)
            if not entity or entity.type != "agent" or not entity.thread_id:
                logger.debug("[deliver] SKIP %s type=%s thread=%s", ce.entity_id, getattr(entity, "type", None), getattr(entity, "thread_id", None))
                continue
            # @@@delivery-strategy-gate — check contact block/mute + chat mute
            # @@@mention-override — mentioned entities skip mute (but not block)
            if self._delivery_resolver:
                from storage.contracts import DeliveryAction
                is_mentioned = ce.entity_id in mentions
                action = self._delivery_resolver.resolve(
                    ce.entity_id, chat_id, sender_entity_id, is_mentioned=is_mentioned,
                )
                if action != DeliveryAction.DELIVER:
                    logger.info("[deliver] POLICY %s for %s (sender=%s chat=%s mentioned=%s)", action.value, ce.entity_id, sender_entity_id, chat_id[:8], is_mentioned)
                    continue
            if self._delivery_fn:
                logger.debug("[deliver] → %s (thread=%s) from=%s", entity.id, entity.thread_id, sender_name)
                try:
                    self._delivery_fn(entity, content, sender_name, chat_id, sender_entity_id)
                except Exception:
                    logger.exception("Failed to deliver chat message to entity %s", entity.id)
            else:
                logger.warning("[deliver] NO delivery_fn for %s", entity.id)

    # @@@owner-agent-rule - owner and own agent use workspace thread, not chat
    def _check_owner_agent_rule(self, entity_ids: list[str]) -> None:
        """Prevent owner <-> own agent from creating a chat."""
        entities = [self._entities.get_by_id(eid) for eid in entity_ids]
        for e in entities:
            if not e:
                raise ValueError(f"Entity not found: {entity_ids}")
            if e.type == "agent":
                agent_member = self._members.get_by_id(e.member_id)
                if not agent_member:
                    continue
                for other in entities:
                    if other and other.id != e.id:
                        other_member = self._members.get_by_id(other.member_id) if other.type == "human" else None
                        if other_member and agent_member.owner_id == other_member.id:
                            raise ValueError("Owner <-> own agent: use workspace, not chat")

    def set_delivery_fn(self, fn) -> None:
        self._delivery_fn = fn

    def list_chats_for_entity(self, entity_id: str) -> list[dict]:
        """List all chats for an entity with summary info."""
        chat_ids = self._chat_entities.list_chats_for_entity(entity_id)
        result = []
        for cid in chat_ids:
            chat = self._chats.get_by_id(cid)
            if not chat or chat.status != "active":
                continue
            participants = self._chat_entities.list_entities(cid)
            entities_info = []
            for p in participants:
                e = self._entities.get_by_id(p.entity_id)
                if e:
                    entities_info.append({"id": e.id, "name": e.name, "type": e.type, "avatar_url": f"/api/members/{e.member_id}/avatar" if e.avatar else None})
            msgs = self._messages.list_by_chat(cid, limit=1)
            last_msg = None
            if msgs:
                m = msgs[0]
                sender = self._entities.get_by_id(m.sender_entity_id)
                last_msg = {"content": m.content, "sender_name": sender.name if sender else "unknown", "created_at": m.created_at}
            unread = self._messages.count_unread(cid, entity_id)
            has_mention = self._messages.has_unread_mention(cid, entity_id)
            result.append({
                "id": cid,
                "title": chat.title,
                "status": chat.status,
                "created_at": chat.created_at,
                "entities": entities_info,
                "last_message": last_msg,
                "unread_count": unread,
                "has_mention": has_mention,
            })
        return result
