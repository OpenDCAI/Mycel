from __future__ import annotations

import asyncio
import json
import threading
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.chat.api.http.dependencies import get_app, get_current_user_id
from backend.threads.chat_adapters.external_inbox_handler import external_inbox_key

router = APIRouter(prefix="/api/runtime", tags=["runtime"])


def chat_runtime_notifications(user_id: str, messaging_service: Any, *, chat_ids: set[str] | None = None) -> list[dict[str, Any]]:
    notifications: list[dict[str, Any]] = []
    for chat in messaging_service.list_chats_for_user(user_id):
        chat_id = str(chat.get("id") or "")
        if chat_ids is not None and chat_id not in chat_ids:
            continue
        unread_count = chat.get("unread_count")
        if type(unread_count) is not int or unread_count <= 0:
            continue
        last_message = chat.get("last_message") or {}
        sender_name = str(last_message.get("sender_name") or "someone")
        notifications.append(
            {
                "event_type": "chat.message",
                "notification_type": "chat",
                "chat_id": chat_id,
                "sender_name": sender_name,
                "unread_count": unread_count,
            }
        )
    return notifications


def drain_runtime_inbox_items(
    user_id: str,
    queue_manager: Any,
    *,
    messaging_service: Any | None = None,
) -> list[dict[str, Any]]:
    items = queue_manager.drain_all(external_inbox_key(user_id))
    drained: list[dict[str, Any]] = []
    chat_ids: set[str] = set()
    for item in items:
        try:
            payload = json.loads(item.content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Invalid external runtime inbox payload") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Invalid external runtime inbox payload")
        payload["notification_type"] = item.notification_type
        payload["source"] = item.source
        payload["sender_id"] = item.sender_id
        payload["sender_name"] = item.sender_name
        if payload["notification_type"] == "chat":
            chat_id = payload.get("chat_id")
            if isinstance(chat_id, str) and chat_id:
                chat_ids.add(chat_id)
            continue
        drained.append(payload)
    if messaging_service is not None and chat_ids:
        drained.extend(chat_runtime_notifications(user_id, messaging_service, chat_ids=chat_ids))
    return drained


def wait_runtime_inbox_items(
    user_id: str,
    queue_manager: Any,
    *,
    timeout_seconds: float,
    messaging_service: Any | None = None,
) -> list[dict[str, Any]]:
    key = external_inbox_key(user_id)
    event = threading.Event()
    queue_manager.register_wake(key, lambda _item: event.set())
    try:
        items = drain_runtime_inbox_items(
            user_id,
            queue_manager,
            messaging_service=messaging_service,
        )
        if items:
            return items
        event.wait(timeout=max(0.0, timeout_seconds))
        return drain_runtime_inbox_items(
            user_id,
            queue_manager,
            messaging_service=messaging_service,
        )
    finally:
        queue_manager.unregister_wake(key)


def _runtime_inbox_parts(app: Any) -> tuple[Any, Any]:
    runtime_state = getattr(app.state, "threads_runtime_state", None)
    queue_manager = getattr(runtime_state, "queue_manager", None)
    if queue_manager is None:
        raise HTTPException(500, "Runtime queue manager unavailable")
    chat_runtime = getattr(app.state, "chat_runtime_state", None)
    messaging_service = getattr(chat_runtime, "messaging_service", None)
    if messaging_service is None:
        raise HTTPException(500, "Messaging service unavailable")
    return queue_manager, messaging_service


@router.post("/inbox/drain")
async def drain_runtime_inbox(
    app: Annotated[Any, Depends(get_app)],
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    queue_manager, messaging_service = _runtime_inbox_parts(app)
    try:
        items = await asyncio.to_thread(
            drain_runtime_inbox_items,
            user_id,
            queue_manager,
            messaging_service=messaging_service,
        )
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"count": len(items), "notifications": items}


@router.post("/inbox/wait")
async def wait_runtime_inbox(
    app: Annotated[Any, Depends(get_app)],
    user_id: Annotated[str, Depends(get_current_user_id)],
    timeout_seconds: Annotated[float, Query(ge=0.0, le=30.0)] = 25.0,
) -> dict[str, Any]:
    queue_manager, messaging_service = _runtime_inbox_parts(app)
    try:
        items = await asyncio.to_thread(
            wait_runtime_inbox_items,
            user_id,
            queue_manager,
            timeout_seconds=timeout_seconds,
            messaging_service=messaging_service,
        )
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"count": len(items), "notifications": items}
