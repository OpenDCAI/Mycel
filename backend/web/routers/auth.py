"""Authentication endpoints — 3-step registration + login."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.web.core.dependencies import _get_auth_service, get_app

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Registration step 1: send OTP ──────────────────────────────────────────

class SendOtpRequest(BaseModel):
    email: str


@router.post("/send-otp")
async def send_otp(payload: SendOtpRequest, app: Annotated[Any, Depends(get_app)]) -> dict:
    try:
        await asyncio.to_thread(_get_auth_service(app).send_otp, payload.email)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Registration step 2: verify OTP ────────────────────────────────────────

class VerifyOtpRequest(BaseModel):
    email: str
    token: str


@router.post("/verify-otp")
async def verify_otp(payload: VerifyOtpRequest, app: Annotated[Any, Depends(get_app)]) -> dict:
    try:
        return await asyncio.to_thread(_get_auth_service(app).verify_register_otp, payload.email, payload.token)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Registration step 3: set password + invite code ────────────────────────

class CompleteRegisterRequest(BaseModel):
    temp_token: str
    password: str
    invite_code: str


@router.post("/complete-register")
async def complete_register(payload: CompleteRegisterRequest, app: Annotated[Any, Depends(get_app)]) -> dict:
    try:
        return await asyncio.to_thread(_get_auth_service(app).complete_register, payload.temp_token, payload.password, payload.invite_code)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Login ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    identifier: str   # email 或 mycel_id（纯数字字符串）
    password: str


@router.post("/login")
async def login(payload: LoginRequest, app: Annotated[Any, Depends(get_app)]) -> dict:
    try:
        return await asyncio.to_thread(_get_auth_service(app).login, payload.identifier, payload.password)
    except ValueError as e:
        raise HTTPException(401, str(e))
