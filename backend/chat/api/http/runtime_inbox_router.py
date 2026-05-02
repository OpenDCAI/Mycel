from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from backend.chat.api.http.dependencies import get_app, get_current_user_id
from backend.chat.runtime_inbox_stream import RuntimeInboxStreamState
from backend.threads.chat_adapters.external_inbox_handler import external_inbox_key

router = APIRouter(prefix="/api/runtime", tags=["runtime"])
logger = logging.getLogger(__name__)


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
                "message_id": last_message.get("id"),
                "message_seq": last_message.get("seq"),
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
            continue
        drained.append(payload)
    if messaging_service is not None:
        drained.extend(chat_runtime_notifications(user_id, messaging_service))
    return drained


def wait_runtime_inbox_items(
    user_id: str,
    queue_manager: Any,
    *,
    timeout_seconds: float,
    messaging_service: Any | None = None,
    wake_bus: Any | None = None,
) -> list[dict[str, Any]]:
    key = external_inbox_key(user_id)
    event = threading.Event()
    if wake_bus is None:
        queue_manager.register_wake(key, lambda _item: event.set())
    else:
        wake_bus.register(key, event.set)
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
        if wake_bus is None:
            queue_manager.unregister_wake(key)
        else:
            wake_bus.unregister(key)


def _runtime_inbox_parts(app: Any) -> tuple[Any, Any, Any, RuntimeInboxStreamState]:
    runtime_state = getattr(app.state, "threads_runtime_state", None)
    queue_manager = getattr(runtime_state, "queue_manager", None)
    if queue_manager is None:
        raise HTTPException(500, "Runtime queue manager unavailable")
    wake_bus = getattr(runtime_state, "runtime_inbox_wake_bus", None)
    if wake_bus is None:
        raise HTTPException(500, "Runtime inbox wake bus unavailable")
    chat_runtime = getattr(app.state, "chat_runtime_state", None)
    messaging_service = getattr(chat_runtime, "messaging_service", None)
    if messaging_service is None:
        raise HTTPException(500, "Messaging service unavailable")
    stream = getattr(runtime_state, "runtime_inbox_stream", None)
    if stream is None:
        raise HTTPException(500, "Runtime inbox stream unavailable")
    return queue_manager, messaging_service, wake_bus, stream


def _runtime_inbox_parts_for_websocket(websocket: WebSocket) -> tuple[Any, Any, Any, RuntimeInboxStreamState]:
    try:
        return _runtime_inbox_parts(websocket.app)
    except HTTPException as exc:
        raise RuntimeError(str(exc.detail)) from exc


async def _websocket_user_id(websocket: WebSocket) -> str:
    authorization = str(websocket.headers.get("authorization") or "")
    token = _authorization_bearer_token(authorization)
    if not token:
        raise RuntimeError("Missing runtime inbox websocket bearer token")
    auth_service = getattr(getattr(websocket.app.state, "auth_runtime_state", None), "auth_service", None)
    if auth_service is None:
        raise RuntimeError("Auth service not initialized")
    payload = auth_service.verify_token(token)
    if not isinstance(payload, dict) or not payload.get("user_id"):
        raise RuntimeError("Invalid runtime inbox websocket token")
    user_id = str(payload["user_id"])
    user_repo = getattr(websocket.app.state, "user_repo", None)
    if user_repo is not None:
        user = await asyncio.to_thread(user_repo.get_by_id, user_id)
        if user is None:
            raise RuntimeError("User no longer exists — please re-login")
    return user_id


def _authorization_bearer_token(authorization: str) -> str | None:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        return token
    return None


def _resume_since_from_payload(payload: Any) -> int | None:
    if not isinstance(payload, dict) or payload.get("type") != "resume":
        return None
    return int(payload.get("since_seq") or 0)


def _sequence_notifications(
    user_id: str,
    notifications: list[dict[str, Any]],
    stream: RuntimeInboxStreamState,
) -> list[dict[str, Any]]:
    if not notifications:
        return []
    return stream.assign(user_id, notifications)


@router.post("/inbox/drain")
async def drain_runtime_inbox(
    app: Annotated[Any, Depends(get_app)],
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    queue_manager, messaging_service, _wake_bus, stream = _runtime_inbox_parts(app)
    try:
        items = await asyncio.to_thread(
            drain_runtime_inbox_items,
            user_id,
            queue_manager,
            messaging_service=messaging_service,
        )
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    items = _sequence_notifications(user_id, items, stream)
    return {"count": len(items), "notifications": items}


@router.post("/inbox/wait")
async def wait_runtime_inbox(
    app: Annotated[Any, Depends(get_app)],
    user_id: Annotated[str, Depends(get_current_user_id)],
    timeout_seconds: Annotated[float, Query(ge=0.0, le=30.0)] = 25.0,
) -> dict[str, Any]:
    queue_manager, messaging_service, wake_bus, stream = _runtime_inbox_parts(app)
    try:
        items = await asyncio.to_thread(
            wait_runtime_inbox_items,
            user_id,
            queue_manager,
            timeout_seconds=timeout_seconds,
            messaging_service=messaging_service,
            wake_bus=wake_bus,
        )
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    items = _sequence_notifications(user_id, items, stream)
    return {"count": len(items), "notifications": items}


@router.websocket("/inbox/subscribe")
async def subscribe_runtime_inbox(websocket: WebSocket) -> None:
    try:
        user_id = await _websocket_user_id(websocket)
        queue_manager, messaging_service, wake_bus, stream = _runtime_inbox_parts_for_websocket(websocket)
    except RuntimeError as exc:
        logger.warning("Runtime inbox websocket rejected: %s", exc)
        await websocket.close(code=1008)
        return
    await websocket.accept()
    inbox_id = external_inbox_key(user_id)
    signal: asyncio.Queue[None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _wake() -> None:
        loop.call_soon_threadsafe(signal.put_nowait, None)

    async def _send_live_notifications() -> bool:
        try:
            items = await asyncio.to_thread(
                drain_runtime_inbox_items,
                user_id,
                queue_manager,
                messaging_service=messaging_service,
            )
        except RuntimeError as exc:
            await websocket.close(code=1011, reason=str(exc))
            return False
        sequenced = stream.assign(user_id, items)
        if not sequenced:
            return True
        since_seq = int(sequenced[0]["seq"]) - 1
        last_seq = int(sequenced[-1]["seq"])
        for frame in stream.frames_between(user_id, after_seq=since_seq, through_seq=last_seq):
            await websocket.send_json(frame)
        return True

    wake_bus.register(inbox_id, _wake)
    try:
        resume_task = asyncio.create_task(websocket.receive_json())
        signal_task = asyncio.create_task(signal.get())
        done, pending = await asyncio.wait({resume_task, signal_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        if resume_task in done:
            since_seq = _resume_since_from_payload(resume_task.result())
            if since_seq is not None:
                for frame in stream.replay_since(user_id, since_seq):
                    await websocket.send_json(frame)
        else:
            if not await _send_live_notifications():
                return
        while True:
            await signal.get()
            if not await _send_live_notifications():
                return
    except WebSocketDisconnect:
        return
    finally:
        wake_bus.unregister(inbox_id)
