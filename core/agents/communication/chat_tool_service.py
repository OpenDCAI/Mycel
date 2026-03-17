"""Chat tool service — 7 tools for entity-to-entity communication.

Tools use entity_ids as parameters.
Two entities share at most one chat; the system auto-resolves entity_id -> chat.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry

logger = logging.getLogger(__name__)


class ChatToolService:
    """Registers 6 chat tools into ToolRegistry.

    Each tool closure captures entity_id (the calling agent's identity)
    and owner_entity_id (for tell_owner gating).
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
        self._register_tell_owner(registry)

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

        def handle(entity_id: str | None = None, chat_id: str | None = None, limit: int = 20, mark_read: bool = True) -> str:
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
            msgs = self._messages.list_by_chat(chat_id, limit=limit)
            if not msgs:
                return "No messages yet."
            if mark_read:
                self._chat_entities.update_last_read(chat_id, eid, time.time())
            lines = []
            for m in msgs:
                sender = self._entities.get_by_id(m.sender_entity_id)
                name = sender.name if sender else "unknown"
                tag = "you" if m.sender_entity_id == eid else name
                lines.append(f"[{tag}]: {m.content}")
            return "\n".join(lines)

        registry.register(ToolEntry(
            name="chat_read",
            mode=ToolMode.INLINE,
            schema={
                "name": "chat_read",
                "description": "Read chat history. Use entity_id for 1:1, chat_id for group chats.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Entity_id for 1:1 chat history"},
                        "chat_id": {"type": "string", "description": "Chat_id for group chat history"},
                        "limit": {"type": "integer", "description": "Max messages to return", "default": 20},
                        "mark_read": {"type": "boolean", "description": "Mark messages as read", "default": True},
                    },
                },
            },
            handler=handle,
            source="chat",
        ))

    def _register_chat_send(self, registry: ToolRegistry) -> None:
        eid = self._entity_id
        owner_eid = self._owner_entity_id

        def handle(content: str, entity_id: str | None = None, chat_id: str | None = None) -> str:
            # @@@group-chat-support - chat_id for groups, entity_id for 1:1
            if chat_id:
                # Direct send to a chat (group or 1:1 by chat_id)
                if not self._chat_entities.is_entity_in_chat(chat_id, eid):
                    raise RuntimeError(f"You are not a member of chat {chat_id}")
                self._chat_service.send_message(chat_id, eid, content)
                return f"Message sent to chat."
            if not entity_id:
                raise RuntimeError("Provide entity_id (for 1:1) or chat_id (for group)")
            # @@@owner-gate - block direct chat to owner; use tell_owner instead
            if entity_id == owner_eid:
                raise RuntimeError("Use tell_owner() to contact your owner, not chat_send.")
            target = self._entities.get_by_id(entity_id)
            if not target:
                raise RuntimeError(f"Entity not found: {entity_id}")
            # @@@reachability-gate - only agent entities with brain threads can receive chat messages
            if target.type != "agent" or not target.thread_id:
                agent_hint = ""
                all_entities = self._entities.list_all()
                for e in all_entities:
                    if e.member_id == target.member_id and e.type == "agent" and e.thread_id:
                        agent_hint = f" Try their agent entity instead: entity_id={e.id} ({e.name})"
                        break
                raise RuntimeError(
                    f"{target.name} is a {target.type} entity and cannot receive chat messages.{agent_hint}"
                )
            chat = self._chat_service.find_or_create_chat([eid, entity_id])
            self._chat_service.send_message(chat.id, eid, content)
            return f"Message sent to {target.name}."

        registry.register(ToolEntry(
            name="chat_send",
            mode=ToolMode.INLINE,
            schema={
                "name": "chat_send",
                "description": (
                    "Send a message. Use entity_id for 1:1 chats, chat_id for group chats.\n\n"
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
                # @@@reachability-tag - show which entities can receive chat messages
                reachable = " ✉" if e.type == "agent" and e.thread_id else ""
                lines.append(f"- {e.name} [{e.type}]{reachable} entity_id={e.id}{owner_info}")
            header = "✉ = can receive chat messages (use their entity_id with chat_send)\n"
            return header + "\n".join(lines)

        registry.register(ToolEntry(
            name="directory",
            mode=ToolMode.INLINE,
            schema={
                "name": "directory",
                "description": "Browse the entity directory. Returns entity_ids for use with chat_send, chat_read. Only entities marked ✉ (agents) can receive chat messages.",
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

    def _register_tell_owner(self, registry: ToolRegistry) -> None:
        runtime_fn = self._runtime_fn

        def handle(message: str) -> str:
            # @@@tell-owner-context-gate — only valid in external runs
            runtime = runtime_fn() if runtime_fn else None
            if runtime and getattr(runtime, "current_run_source", None) == "owner":
                raise RuntimeError(
                    "Your owner is right here in this conversation — just say it directly. "
                    "tell_owner is for external conversations when your owner isn't present."
                )
            logger.info("[tell_owner] %s", message[:100])
            return f"Owner notified: {message}"

        registry.register(ToolEntry(
            name="tell_owner",
            mode=ToolMode.INLINE,
            schema={
                "name": "tell_owner",
                "description": (
                    "Notify your owner about something important. "
                    "ONLY use this during external conversations (when someone else messaged you). "
                    "Do NOT use this when your owner is already talking to you — just respond directly."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "The message for your owner"},
                    },
                    "required": ["message"],
                },
            },
            handler=handle,
            source="chat",
        ))

