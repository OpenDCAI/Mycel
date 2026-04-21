"""Unified conversation list API — chat/backend owner module."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from backend.chat.api.http.dependencies import get_app, get_current_user_id
from backend.identity.avatar.urls import avatar_url
from backend.threads.owner_reads import list_owner_thread_rows_for_auth_burst
from backend.threads.projection import canonical_owner_threads
from protocols.runtime_read import RuntimeThreadActivityReader

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _is_internal_child_thread(thread_id: str) -> bool:
    return thread_id.startswith("subagent-")


def _conversation_updated_at_key(item: dict[str, Any]) -> float:
    raw = item.get("updated_at")
    if raw is None:
        return float("-inf")
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw).timestamp()
        except ValueError:
            return float("-inf")
    return float("-inf")


@router.get("")
async def list_conversations(
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)] = None,
) -> list[dict[str, Any]]:
    raw_threads, visit_items = await asyncio.gather(
        list_owner_thread_rows_for_auth_burst(app, user_id),
        asyncio.to_thread(_list_visit_conversations_for_user, app, user_id),
    )
    hire_items = await asyncio.to_thread(_list_hire_conversations_from_threads, app, raw_threads)
    return _sort_conversation_items([*hire_items, *visit_items])


def _list_hire_conversations_from_threads(app: Any, raw_thread_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    raw_threads = canonical_owner_threads(raw_thread_rows)
    activity_reader = getattr(app.state, "agent_runtime_thread_activity_reader", None)
    for t in raw_threads:
        tid = t["id"]
        if _is_internal_child_thread(tid):
            continue
        running = _thread_running(activity_reader, t.get("agent_user_id"), tid)
        last_active = app.state.thread_last_active.get(tid)
        updated_at = datetime.fromtimestamp(last_active, tz=UTC).isoformat() if last_active else None
        items.append(
            {
                "id": tid,
                "type": "hire",
                "title": t.get("agent_name") or "Agent",
                "avatar_url": avatar_url(t.get("agent_user_id"), bool(t.get("agent_avatar"))),
                "updated_at": updated_at,
                "unread_count": 0,
                "running": running,
            }
        )
    return items


def _thread_running(activity_reader: RuntimeThreadActivityReader | None, agent_user_id: Any, thread_id: str) -> bool:
    if activity_reader is None:
        return False
    normalized_agent_user_id = str(agent_user_id or "").strip()
    if not normalized_agent_user_id:
        return False
    return any(
        activity.thread_id == thread_id and activity.state == "active"
        for activity in activity_reader.list_active_threads_for_agent(normalized_agent_user_id)
    )


def _list_visit_conversations_for_user(app: Any, user_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    messaging = getattr(app.state, "messaging_service", None)
    if messaging:
        chats = messaging.list_conversation_summaries_for_user(user_id)
        for chat in chats:
            items.append(
                {
                    "id": chat["id"],
                    "type": "visit",
                    "title": chat.get("title") or "Chat",
                    "avatar_url": chat.get("avatar_url"),
                    "updated_at": chat.get("updated_at") or chat.get("created_at"),
                    "unread_count": chat.get("unread_count", 0),
                    "running": False,
                }
            )
    return items


def _sort_conversation_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items.sort(key=_conversation_updated_at_key, reverse=True)
    return items
