from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from backend.chat.api.http.dependencies import get_app, get_current_user_id
from backend.threads.chat_adapters.external_inbox_handler import external_inbox_key

router = APIRouter(prefix="/api/runtime", tags=["runtime"])


def drain_runtime_inbox_items(user_id: str, queue_manager: Any) -> list[dict[str, Any]]:
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
        drained.append(payload)
    return drained


@router.post("/inbox/drain")
async def drain_runtime_inbox(
    app: Annotated[Any, Depends(get_app)],
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    runtime_state = getattr(app.state, "threads_runtime_state", None)
    queue_manager = getattr(runtime_state, "queue_manager", None)
    if queue_manager is None:
        raise HTTPException(500, "Runtime queue manager unavailable")
    try:
        items = await asyncio.to_thread(drain_runtime_inbox_items, user_id, queue_manager)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"count": len(items), "notifications": items}
