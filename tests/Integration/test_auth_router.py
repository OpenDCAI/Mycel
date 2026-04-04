from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.routers import auth as auth_router
from backend.web.routers import chats as chats_router


class _FakeAuthService:
    def __init__(self) -> None:
        self.register_calls: list[tuple[str, str]] = []
        self.login_calls: list[tuple[str, str]] = []
        self.register_result = {"token": "tok-register"}
        self.login_result = {"token": "tok-login"}
        self.register_error: Exception | None = None
        self.login_error: Exception | None = None

    def register(self, username: str, password: str) -> dict:
        self.register_calls.append((username, password))
        if self.register_error is not None:
            raise self.register_error
        return self.register_result

    def login(self, username: str, password: str) -> dict:
        self.login_calls.append((username, password))
        if self.login_error is not None:
            raise self.login_error
        return self.login_result


@pytest.mark.asyncio
async def test_register_calls_auth_service_directly():
    service = _FakeAuthService()
    app = SimpleNamespace(state=SimpleNamespace(auth_service=service))

    result = await auth_router.register(auth_router.AuthRequest(username="fresh", password="pass1234"), app)

    assert result == {"token": "tok-register"}
    assert service.register_calls == [("fresh", "pass1234")]


@pytest.mark.asyncio
async def test_register_maps_value_error_to_conflict():
    service = _FakeAuthService()
    service.register_error = ValueError("Username 'fresh' already taken")
    app = SimpleNamespace(state=SimpleNamespace(auth_service=service))

    with pytest.raises(HTTPException) as exc_info:
        await auth_router.register(auth_router.AuthRequest(username="fresh", password="pass1234"), app)

    assert exc_info.value.status_code == 409
    assert "already taken" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_login_calls_auth_service_directly():
    service = _FakeAuthService()
    app = SimpleNamespace(state=SimpleNamespace(auth_service=service))

    result = await auth_router.login(auth_router.AuthRequest(username="fresh", password="pass1234"), app)

    assert result == {"token": "tok-login"}
    assert service.login_calls == [("fresh", "pass1234")]


@pytest.mark.asyncio
async def test_login_maps_value_error_to_unauthorized():
    service = _FakeAuthService()
    service.login_error = ValueError("Invalid username or password")
    app = SimpleNamespace(state=SimpleNamespace(auth_service=service))

    with pytest.raises(HTTPException) as exc_info:
        await auth_router.login(auth_router.AuthRequest(username="fresh", password="pass1234"), app)

    assert exc_info.value.status_code == 401
    assert "Invalid username or password" in str(exc_info.value.detail)


class _VerifyOnlyAuthService:
    def __init__(self) -> None:
        self.tokens: list[str] = []

    def verify_token(self, token: str) -> dict:
        self.tokens.append(token)
        return {"user_id": "user-1"}


@pytest.mark.asyncio
async def test_chat_events_requires_token():
    app = SimpleNamespace(
        state=SimpleNamespace(
            auth_service=_VerifyOnlyAuthService(),
            chat_event_bus=SimpleNamespace(subscribe=lambda _chat_id: None),
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await chats_router.stream_chat_events("chat-1", token=None, app=app)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Missing token"


@pytest.mark.asyncio
async def test_chat_events_verifies_provided_token():
    auth_service = _VerifyOnlyAuthService()
    app = SimpleNamespace(
        state=SimpleNamespace(
            auth_service=auth_service,
            chat_event_bus=SimpleNamespace(subscribe=lambda _chat_id: None),
        )
    )

    response = await chats_router.stream_chat_events("chat-1", token="tok-chat", app=app)

    assert auth_service.tokens == ["tok-chat"]
    assert response.media_type == "text/event-stream"
