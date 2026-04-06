"""Authentication endpoints — 3-step registration + login."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.web.core.dependencies import _get_auth_service, get_app

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _call_auth_service(app: Any, status_code: int, method_name: str, *args: Any) -> Any:
    try:
        service = _get_auth_service(app)
        method = getattr(service, method_name)
        return await asyncio.to_thread(method, *args)
    except ValueError as e:
        raise HTTPException(status_code, str(e))


# ── Registration step 1: send OTP ──────────────────────────────────────────


class SendOtpRequest(BaseModel):
    email: str
    password: str
    invite_code: str


@router.post("/send-otp")
async def send_otp(payload: SendOtpRequest, app: Annotated[Any, Depends(get_app)]) -> dict:
    await _call_auth_service(app, 400, "send_otp", payload.email, payload.password, payload.invite_code)
    return {"ok": True}


# ── Registration step 2: verify OTP ────────────────────────────────────────


class VerifyOtpRequest(BaseModel):
    email: str
    token: str


@router.post("/verify-otp")
async def verify_otp(payload: VerifyOtpRequest, app: Annotated[Any, Depends(get_app)]) -> dict:
    return await _call_auth_service(app, 400, "verify_register_otp", payload.email, payload.token)


# ── Registration step 3: set password + invite code ────────────────────────


class CompleteRegisterRequest(BaseModel):
    temp_token: str
    invite_code: str


@router.post("/complete-register")
async def complete_register(payload: CompleteRegisterRequest, app: Annotated[Any, Depends(get_app)]) -> dict:
    return await _call_auth_service(app, 400, "complete_register", payload.temp_token, payload.invite_code)


# ── Login ───────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    identifier: str  # email 或 mycel_id（纯数字字符串）
    password: str


@router.post("/login")
async def login(payload: LoginRequest, app: Annotated[Any, Depends(get_app)]) -> dict:
    return await _call_auth_service(app, 401, "login", payload.identifier, payload.password)
