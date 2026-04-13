"""Invite code management endpoints."""

import asyncio
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.web.core.dependencies import get_current_user_id
from storage.contracts import InviteCodeRepo

router = APIRouter(prefix="/api/invite-codes", tags=["invite-codes"])


def _invite_code_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "used": bool(row.get("used_by"))}


def _invite_code_repo(request: Request) -> InviteCodeRepo:
    sb_client = getattr(request.app.state, "_supabase_client", None)
    if sb_client is None:
        raise HTTPException(503, "邀请码服务不可用（当前为 SQLite 模式）")
    repo = getattr(request.app.state, "invite_code_repo", None)
    if repo is None:
        raise HTTPException(503, "邀请码仓库未初始化")
    return repo


async def _call_invite_code_repo(error_prefix: str, call: Callable[[], Any]) -> Any:
    try:
        return await asyncio.to_thread(call)
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
    repo = _invite_code_repo(request)
    codes = await _call_invite_code_repo("获取邀请码列表失败：", repo.list_all)
    return {"codes": [_invite_code_payload(code) for code in codes]}


# ── Generate a new invite code ───────────────────────────────────────────────


class GenerateInviteCodeRequest(BaseModel):
    expires_days: int | None = 7


@router.post("")
async def generate_invite_code(
    payload: GenerateInviteCodeRequest,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict:
    repo = _invite_code_repo(request)
    code = await _call_invite_code_repo(
        "生成邀请码失败：",
        lambda: repo.generate(created_by=user_id, expires_days=payload.expires_days),
    )
    return _invite_code_payload(code)


# ── Revoke (delete) an invite code ──────────────────────────────────────────


@router.delete("/{code}")
async def revoke_invite_code(
    code: str,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict:
    repo = _invite_code_repo(request)
    ok = await _call_invite_code_repo("吊销邀请码失败：", lambda: repo.revoke(code))
    if not ok:
        raise HTTPException(404, "邀请码不存在")
    return {"ok": True}


# ── Validate an invite code (no auth required) ───────────────────────────────


@router.get("/validate/{code}")
async def validate_invite_code(code: str, request: Request) -> dict:
    repo = _invite_code_repo(request)
    valid = await _call_invite_code_repo("校验邀请码失败：", lambda: repo.is_valid(code))
    return {"valid": valid}
