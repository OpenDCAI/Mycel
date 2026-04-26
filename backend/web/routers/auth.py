import asyncio
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.identity.auth.dependencies import _get_auth_service
from backend.identity.auth.service import ExternalUserAlreadyExistsError
from backend.web.core.dependencies import get_app, get_current_user, get_current_user_id

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _call_auth_service(app: Any, status_code: int, call: Callable[[Any], Any]) -> Any:
    try:
        service = _get_auth_service(app)
        return await asyncio.to_thread(call, service)
    except ValueError as e:
        raise HTTPException(status_code, str(e))


class SendOtpRequest(BaseModel):
    email: str
    password: str
    invite_code: str


@router.post("/send-otp")
async def send_otp(payload: SendOtpRequest, app: Annotated[Any, Depends(get_app)]) -> dict:
    await _call_auth_service(
        app,
        400,
        lambda service: service.send_otp(payload.email, payload.password, payload.invite_code),
    )
    return {"ok": True}


class VerifyOtpRequest(BaseModel):
    email: str
    token: str


@router.post("/verify-otp")
async def verify_otp(payload: VerifyOtpRequest, app: Annotated[Any, Depends(get_app)]) -> dict:
    return await _call_auth_service(
        app,
        400,
        lambda service: service.verify_register_otp(payload.email, payload.token),
    )


class CompleteRegisterRequest(BaseModel):
    temp_token: str
    invite_code: str


@router.post("/complete-register")
async def complete_register(payload: CompleteRegisterRequest, app: Annotated[Any, Depends(get_app)]) -> dict:
    return await _call_auth_service(
        app,
        400,
        lambda service: service.complete_register(payload.temp_token, payload.invite_code),
    )


class LoginRequest(BaseModel):
    identifier: str  # email 或 mycel_id（纯数字字符串）
    password: str


@router.post("/login")
async def login(payload: LoginRequest, app: Annotated[Any, Depends(get_app)]) -> dict:
    return await _call_auth_service(
        app,
        401,
        lambda service: service.login(payload.identifier, payload.password),
    )


class CreateExternalUserRequest(BaseModel):
    user_id: str
    display_name: str


@router.get("/me")
async def me(user: Annotated[Any, Depends(get_current_user)]) -> dict:
    user_type = getattr(user.type, "value", user.type)
    return {
        "id": user.id,
        "name": user.display_name,
        "type": user_type,
        "email": user.email,
        "mycel_id": user.mycel_id,
        "avatar": user.avatar,
    }


@router.post("/external-users")
async def create_external_user(
    payload: CreateExternalUserRequest,
    app: Annotated[Any, Depends(get_app)],
    current_user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict:
    try:
        return await asyncio.to_thread(
            lambda: _get_auth_service(app).create_external_user_token(
                payload.user_id,
                payload.display_name,
                created_by_user_id=current_user_id,
            )
        )
    except ExternalUserAlreadyExistsError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
