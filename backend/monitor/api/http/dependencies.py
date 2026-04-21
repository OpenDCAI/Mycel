"""Monitor router dependency helpers."""

from __future__ import annotations

from fastapi import FastAPI, Request

from backend.identity.auth.user_resolution import get_current_user_id

__all__ = ["get_app", "get_current_user_id"]


async def get_app(request: Request) -> FastAPI:
    return request.app
