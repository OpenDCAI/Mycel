"""Authentication endpoints — register and login."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.web.core.dependencies import get_app

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AuthRequest(BaseModel):
    username: str
    password: str


@router.post("/register")
async def register(payload: AuthRequest, app: Annotated[Any, Depends(get_app)]) -> dict:
    auth_service = getattr(app.state, "auth_service", None)
    if auth_service is None:
        raise HTTPException(500, "Auth service not initialized")
    try:
        return auth_service.register(payload.username, payload.password)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/login")
async def login(payload: AuthRequest, app: Annotated[Any, Depends(get_app)]) -> dict:
    auth_service = getattr(app.state, "auth_service", None)
    if auth_service is None:
        raise HTTPException(500, "Auth service not initialized")
    try:
        return auth_service.login(payload.username, payload.password)
    except ValueError as e:
        raise HTTPException(401, str(e))
