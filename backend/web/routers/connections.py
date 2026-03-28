"""Connection endpoints — manage external platform connections (WeChat, etc.).

@@@per-user — all endpoints scoped by entity_id (the user's social identity).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from backend.web.core.dependencies import get_app, get_current_entity_id, get_current_user_id
from backend.web.services.wechat_service import (
    QrPollRequest,
    RoutingConfig,
    RoutingSetRequest,
    WeChatConnectionRegistry,
)

router = APIRouter(prefix="/api/connections", tags=["connections"])


def _get_registry(app: Any) -> WeChatConnectionRegistry:
    return app.state.wechat_registry


# --- WeChat ---


@router.get("/wechat/state")
async def wechat_state(
    entity_id: Annotated[str, Depends(get_current_entity_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict:
    return _get_registry(app).get(entity_id).get_state()


@router.post("/wechat/qrcode")
async def wechat_qrcode(
    entity_id: Annotated[str, Depends(get_current_entity_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict:
    conn = _get_registry(app).get(entity_id)
    if conn.connected:
        raise HTTPException(400, "Already connected. Disconnect first.")
    return await conn.get_qr_code()


@router.post("/wechat/qrcode/poll")
async def wechat_qrcode_poll(
    body: QrPollRequest,
    entity_id: Annotated[str, Depends(get_current_entity_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict:
    registry = _get_registry(app)
    conn = registry.get(entity_id)
    result = await conn.poll_qr_status(body.qrcode)
    # Evict duplicates after successful connection
    if result.get("status") == "confirmed" and conn._credentials:
        registry.evict_duplicates(conn._credentials.account_id, entity_id)
    return result


@router.post("/wechat/disconnect")
async def wechat_disconnect(
    entity_id: Annotated[str, Depends(get_current_entity_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict:
    _get_registry(app).get(entity_id).disconnect()
    return {"ok": True}


@router.post("/wechat/polling/start")
async def wechat_start_polling(
    entity_id: Annotated[str, Depends(get_current_entity_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict:
    conn = _get_registry(app).get(entity_id)
    if not conn.connected:
        raise HTTPException(400, "Not connected")
    conn.start_polling()
    return {"ok": True, "polling": True}


@router.post("/wechat/polling/stop")
async def wechat_stop_polling(
    entity_id: Annotated[str, Depends(get_current_entity_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict:
    _get_registry(app).get(entity_id).stop_polling()
    return {"ok": True, "polling": False}


# --- Routing config ---


@router.get("/wechat/routing")
async def wechat_get_routing(
    entity_id: Annotated[str, Depends(get_current_entity_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict:
    return _get_registry(app).get(entity_id).routing.model_dump()


@router.post("/wechat/routing")
async def wechat_set_routing(
    body: RoutingSetRequest,
    entity_id: Annotated[str, Depends(get_current_entity_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict:
    _get_registry(app).get(entity_id).set_routing(
        RoutingConfig(type=body.type, id=body.id, label=body.label)
    )
    return {"ok": True}


@router.delete("/wechat/routing")
async def wechat_clear_routing(
    entity_id: Annotated[str, Depends(get_current_entity_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict:
    _get_registry(app).get(entity_id).set_routing(RoutingConfig())
    return {"ok": True}


# --- List targets for routing picker ---


@router.get("/wechat/routing/targets")
async def wechat_routing_targets(
    user_id: Annotated[str, Depends(get_current_user_id)],
    entity_id: Annotated[str, Depends(get_current_entity_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict:
    """List available threads and chats for the routing picker.

    user_id: needed for thread ownership lookup (threads belong to agent members owned by this user).
    entity_id: needed for chat lookup (chats the user's social identity participates in).
    """
    from backend.web.utils.serializers import avatar_url
    raw_threads = app.state.thread_repo.list_by_owner_user_id(user_id)
    threads = [
        {
            "id": t["id"],
            "label": t.get("entity_name") or t.get("member_name") or t["id"][:12],
            "avatar_url": avatar_url(t.get("member_id"), bool(t.get("member_avatar"))),
        }
        for t in raw_threads
    ]

    raw_chats = app.state.chat_service.list_chats_for_entity(entity_id)
    chats = []
    for c in raw_chats:
        others = [e for e in c.get("entities", []) if e["id"] != entity_id]
        name = ", ".join(e["name"] for e in others) or "Unknown"
        chats.append({"id": c["id"], "label": name})

    return {"threads": threads, "chats": chats}
