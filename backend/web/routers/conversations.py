"""Unified conversation list API — merges threads (hire) and chats (visit).

GET /api/conversations returns a single sorted list so the frontend
ConversationList can render a unified sidebar.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from backend.web.core.dependencies import get_app, get_current_user_id
from backend.web.utils.serializers import avatar_url
from core.runtime.middleware.monitor import AgentState

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
        # @@@mixed-updated-at-sort - hire rows currently carry ISO strings while
        # visit chats can still surface numeric timestamps from older chat storage.
        # Normalize both before sorting so /api/conversations stays honest.
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return float("-inf")
    return float("-inf")


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
                "title": t.get("agent_name") or "Agent",
                "avatar_url": avatar_url(t.get("agent_user_id"), bool(t.get("agent_avatar"))),
                "updated_at": updated_at,
                "unread_count": 0,
                "running": running,
            }
        )

    # ── Visit chats ──
    messaging = getattr(app.state, "messaging_service", None)
    if messaging:
        chats = messaging.list_chats_for_user(user_id)
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

    # Sort by updated_at descending (None goes last)
    items.sort(key=_conversation_updated_at_key, reverse=True)
    return items
