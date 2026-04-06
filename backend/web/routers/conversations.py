"""Unified conversation list API — merges threads (hire) and chats (visit).

GET /api/conversations returns a single sorted list so the frontend
ConversationList can render a unified sidebar.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from backend.web.core.dependencies import get_app, get_current_user_id
from backend.web.utils.serializers import avatar_url
from core.runtime.middleware.monitor import AgentState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _is_internal_child_thread(thread_id: str) -> bool:
    return thread_id.startswith("subagent-")


@router.get("")
async def list_conversations(
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)] = None,
) -> list[dict[str, Any]]:
    """Return hire threads + visit chats merged by updated_at desc."""
    items: list[dict[str, Any]] = []

    # ── Hire threads ──
    raw_threads = app.state.thread_repo.list_by_owner_user_id(user_id)
    pool = app.state.agent_pool
    for t in raw_threads:
        tid = t["id"]
        if _is_internal_child_thread(tid):
            continue
        sandbox_type = t.get("sandbox_type", "local")
        running = False
        agent = pool.get(f"{tid}:{sandbox_type}")
        if agent and hasattr(agent, "runtime"):
            running = agent.runtime.current_state == AgentState.ACTIVE
        last_active = app.state.thread_last_active.get(tid)
        updated_at = datetime.fromtimestamp(last_active, tz=UTC).isoformat() if last_active else None
        items.append(
            {
                "id": tid,
                "type": "hire",
                "title": t.get("member_name") or "Agent",
                "member_id": t.get("member_id"),
                "avatar_url": avatar_url(t.get("member_id"), bool(t.get("member_avatar"))),
                "updated_at": updated_at,
                "unread_count": 0,
                "running": running,
            }
        )

    # ── Visit chats ──
    messaging = getattr(app.state, "messaging_service", None)
    if messaging:
        chats = messaging.list_chats_for_user(user_id)
        member_repo = app.state.member_repo
        messages_repo = getattr(app.state, "messages_repo", None)

        # Pre-fetch all member data to avoid N+1 per-member lookups
        all_member_ids: set[str] = set()
        chat_members_cache: dict[str, list[dict[str, Any]]] = {}
        chat_obj_cache: dict[str, Any] = {}

        chat_ids = [c["id"] if isinstance(c, dict) else c for c in chats]
        for chat_id in chat_ids:
            chat_obj = app.state.chat_repo.get_by_id(chat_id) if hasattr(app.state, "chat_repo") else None
            if not chat_obj:
                continue
            chat_obj_cache[chat_id] = chat_obj
            members_list = messaging.list_chat_members(chat_id)
            chat_members_cache[chat_id] = members_list
            for m in members_list:
                uid = m.get("user_id")
                if uid and uid != user_id:
                    all_member_ids.add(uid)

        # Batch resolve members
        member_cache: dict[str, Any] = {}
        for uid in all_member_ids:
            mem = member_repo.get_by_id(uid)
            if mem:
                member_cache[uid] = mem

        for chat_id in chat_ids:
            chat_obj = chat_obj_cache.get(chat_id)
            if not chat_obj:
                continue
            members_list = chat_members_cache[chat_id]

            # Determine display name + avatar in single pass
            title = getattr(chat_obj, "title", None) or ""
            chat_avatar = None
            other_names: list[str] = []
            for m in members_list:
                uid = m.get("user_id")
                if not uid or uid == user_id:
                    continue
                mem = member_cache.get(uid)
                if not mem:
                    continue
                other_names.append(mem.name)
                if chat_avatar is None:
                    chat_avatar = avatar_url(mem.id, bool(mem.avatar))
            if not title:
                title = ", ".join(other_names) or "Chat"

            # Unread count
            unread = 0
            if messages_repo:
                unread = messages_repo.count_unread(chat_id, user_id)

            items.append(
                {
                    "id": chat_id,
                    "type": "visit",
                    "title": title,
                    "member_id": None,
                    "avatar_url": chat_avatar,
                    "updated_at": getattr(chat_obj, "updated_at", None) or getattr(chat_obj, "created_at", None),
                    "unread_count": unread,
                    "running": False,
                }
            )

    # Sort by updated_at descending (None goes last)
    items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return items
