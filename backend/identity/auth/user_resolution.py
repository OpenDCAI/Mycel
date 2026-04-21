"""Neutral current-user resolution helpers."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import HTTPException, Request

from backend.identity.auth.dependencies import _get_auth_service


def _extract_jwt_payload(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")
    token = auth_header[7:]
    try:
        return _get_auth_service(request.app).verify_token(token)
    except ValueError as e:
        raise HTTPException(401, str(e))


async def _get_user_row_for_auth(request: Request, user_id: str, user_repo: Any) -> Any:
    state = request.app.state
    guard = getattr(state, "_auth_user_check_guard", None)
    if guard is None:
        guard = asyncio.Lock()
        setattr(state, "_auth_user_check_guard", guard)
    inflight = getattr(state, "_auth_user_check_inflight", None)
    if inflight is None:
        inflight = {}
        setattr(state, "_auth_user_check_inflight", inflight)

    async with guard:
        task = inflight.get(user_id)
        owns_task = task is None
        if task is None:
            task = asyncio.create_task(asyncio.to_thread(user_repo.get_by_id, user_id))
            inflight[user_id] = task

    try:
        return await task
    finally:
        if owns_task:
            async with guard:
                if inflight.get(user_id) is task:
                    del inflight[user_id]


async def _resolve_current_user(request: Request) -> tuple[str, Any | None]:
    user_id = _extract_jwt_payload(request)["user_id"]
    user_repo = getattr(request.app.state, "user_repo", None)
    if user_repo is None:
        return user_id, None
    user = await _get_user_row_for_auth(request, user_id, user_repo)
    if user is None:
        raise HTTPException(401, "User no longer exists — please re-login")
    return user_id, user


async def get_current_user(request: Request) -> Any:
    _, user = await _resolve_current_user(request)
    if user is None:
        raise HTTPException(500, "User repo not initialized")
    return user


async def get_current_user_id(request: Request) -> str:
    user_id, _ = await _resolve_current_user(request)
    return user_id
