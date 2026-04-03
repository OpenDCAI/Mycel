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


# ── List all invite codes ────────────────────────────────────────────────────


@router.get("")
async def list_invite_codes(
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict:
    repo = _get_invite_code_repo(request.app)
    try:
        codes = await asyncio.to_thread(repo.list_all)
        return {"codes": codes}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"获取邀请码列表失败：{e}") from e


# ── Generate a new invite code ───────────────────────────────────────────────


class GenerateInviteCodeRequest(BaseModel):
    expires_days: int | None = 7


@router.post("")
async def generate_invite_code(
    payload: GenerateInviteCodeRequest,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict:
    repo = _get_invite_code_repo(request.app)
    try:
        code = await asyncio.to_thread(
            repo.generate,
            created_by=user_id,
            expires_days=payload.expires_days,
        )
        return code
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"生成邀请码失败：{e}") from e


# ── Revoke (delete) an invite code ──────────────────────────────────────────


@router.delete("/{code}")
async def revoke_invite_code(
    code: str,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict:
    repo = _get_invite_code_repo(request.app)
    try:
        ok = await asyncio.to_thread(repo.revoke, code)
        if not ok:
            raise HTTPException(404, "邀请码不存在")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"吊销邀请码失败：{e}") from e


# ── Validate an invite code (no auth required) ───────────────────────────────


@router.get("/validate/{code}")
async def validate_invite_code(code: str, request: Request) -> dict:
    repo = _get_invite_code_repo(request.app)
    try:
        valid = await asyncio.to_thread(repo.is_valid, code)
        return {"valid": valid}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"校验邀请码失败：{e}") from e
