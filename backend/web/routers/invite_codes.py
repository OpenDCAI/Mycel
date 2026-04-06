"""Invite code management endpoints."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.web.core.dependencies import get_current_user_id

router = APIRouter(prefix="/api/invite-codes", tags=["invite-codes"])


def _get_invite_code_repo(app: Any):
    """Get SupabaseInviteCodeRepo from app state, or raise 503 if unavailable."""
    sb_client = getattr(app.state, "_supabase_client", None)
    if sb_client is None:
        raise HTTPException(503, "邀请码服务不可用（当前为 SQLite 模式）")
    repo = getattr(app.state, "invite_code_repo", None)
    if repo is None:
        raise HTTPException(503, "邀请码仓库未初始化")
    return repo


async def _call_invite_code_repo(
    request: Request,
    error_prefix: str,
    method_name: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    repo = _get_invite_code_repo(request.app)
    try:
        method = getattr(repo, method_name)
        return await asyncio.to_thread(method, *args, **kwargs)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"{error_prefix}{e}") from e


# ── List all invite codes ────────────────────────────────────────────────────


@router.get("")
async def list_invite_codes(
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict:
    codes = await _call_invite_code_repo(request, "获取邀请码列表失败：", "list_all")
    return {"codes": codes}


# ── Generate a new invite code ───────────────────────────────────────────────


class GenerateInviteCodeRequest(BaseModel):
    expires_days: int | None = 7


@router.post("")
async def generate_invite_code(
    payload: GenerateInviteCodeRequest,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict:
    return await _call_invite_code_repo(
        request,
        "生成邀请码失败：",
        "generate",
        created_by=user_id,
        expires_days=payload.expires_days,
    )


# ── Revoke (delete) an invite code ──────────────────────────────────────────


@router.delete("/{code}")
async def revoke_invite_code(
    code: str,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict:
    ok = await _call_invite_code_repo(request, "吊销邀请码失败：", "revoke", code)
    if not ok:
        raise HTTPException(404, "邀请码不存在")
    return {"ok": True}


# ── Validate an invite code (no auth required) ───────────────────────────────


@router.get("/validate/{code}")
async def validate_invite_code(code: str, request: Request) -> dict:
    valid = await _call_invite_code_repo(request, "校验邀请码失败：", "is_valid", code)
    return {"valid": valid}
