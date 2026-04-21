"""Chat HTTP dependency helpers."""

from fastapi import FastAPI, Request

from backend.identity.auth.user_resolution import get_current_user_id as resolve_current_user_id

get_current_user_id = resolve_current_user_id


async def get_app(request: Request) -> FastAPI:
    return request.app
