from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.routers import auth as auth_router
from backend.web.routers import messaging as chats_router


class _FakeAuthService:
    def __init__(self) -> None:
        self.send_otp_calls: list[tuple[str, str, str]] = []
        self.verify_otp_calls: list[tuple[str, str]] = []
        self.complete_register_calls: list[tuple[str, str]] = []
        self.login_calls: list[tuple[str, str]] = []
        self.verify_otp_result = {"temp_token": "temp-otp"}
        self.complete_register_result = {"token": "tok-register"}
        self.login_result = {"token": "tok-login"}
        self.send_otp_error: Exception | None = None
        self.verify_otp_error: Exception | None = None
        self.complete_register_error: Exception | None = None
        self.login_error: Exception | None = None

    def send_otp(self, email: str, password: str, invite_code: str) -> None:
        self.send_otp_calls.append((email, password, invite_code))
        if self.send_otp_error is not None:
            raise self.send_otp_error

    def verify_register_otp(self, email: str, token: str) -> dict:
        self.verify_otp_calls.append((email, token))
        if self.verify_otp_error is not None:
            raise self.verify_otp_error
        return self.verify_otp_result

    def complete_register(self, temp_token: str, invite_code: str) -> dict:
        self.complete_register_calls.append((temp_token, invite_code))
        if self.complete_register_error is not None:
            raise self.complete_register_error
        return self.complete_register_result

    def login(self, identifier: str, password: str) -> dict:
        self.login_calls.append((identifier, password))
        if self.login_error is not None:
            raise self.login_error
        return self.login_result


@pytest.mark.asyncio
async def test_send_otp_calls_auth_service_directly():
    service = _FakeAuthService()
    app = SimpleNamespace(state=SimpleNamespace(auth_service=service))

    result = await auth_router.send_otp(
        auth_router.SendOtpRequest(email="fresh@example.com", password="pass1234", invite_code="invite-1"),
        app,
    )

    assert result == {"ok": True}
    assert service.send_otp_calls == [("fresh@example.com", "pass1234", "invite-1")]


@pytest.mark.asyncio
async def test_send_otp_maps_value_error_to_bad_request():
    service = _FakeAuthService()
    service.send_otp_error = ValueError("邀请码无效或已过期")
    app = SimpleNamespace(state=SimpleNamespace(auth_service=service))

    with pytest.raises(HTTPException) as exc_info:
        await auth_router.send_otp(
            auth_router.SendOtpRequest(email="fresh@example.com", password="pass1234", invite_code="invite-1"),
            app,
        )

    assert exc_info.value.status_code == 400
    assert "邀请码无效" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_verify_otp_calls_auth_service_directly():
    service = _FakeAuthService()
    app = SimpleNamespace(state=SimpleNamespace(auth_service=service))

    result = await auth_router.verify_otp(
        auth_router.VerifyOtpRequest(email="fresh@example.com", token="123456"),
        app,
    )

    assert result == {"temp_token": "temp-otp"}
    assert service.verify_otp_calls == [("fresh@example.com", "123456")]


@pytest.mark.asyncio
async def test_complete_register_calls_auth_service_directly():
    service = _FakeAuthService()
    app = SimpleNamespace(state=SimpleNamespace(auth_service=service))

    result = await auth_router.complete_register(
        auth_router.CompleteRegisterRequest(temp_token="temp-otp", invite_code="invite-1"),
        app,
    )

    assert result == {"token": "tok-register"}
    assert service.complete_register_calls == [("temp-otp", "invite-1")]


@pytest.mark.asyncio
async def test_login_calls_auth_service_directly():
    service = _FakeAuthService()
    app = SimpleNamespace(state=SimpleNamespace(auth_service=service))

    result = await auth_router.login(auth_router.LoginRequest(identifier="fresh@example.com", password="pass1234"), app)

    assert result == {"token": "tok-login"}
    assert service.login_calls == [("fresh@example.com", "pass1234")]


@pytest.mark.asyncio
async def test_login_maps_value_error_to_unauthorized():
    service = _FakeAuthService()
    service.login_error = ValueError("Invalid username or password")
    app = SimpleNamespace(state=SimpleNamespace(auth_service=service))

    with pytest.raises(HTTPException) as exc_info:
        await auth_router.login(auth_router.LoginRequest(identifier="fresh@example.com", password="pass1234"), app)

    assert exc_info.value.status_code == 401
    assert "Invalid username or password" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_call_auth_service_returns_service_result():
    service = _FakeAuthService()
    app = SimpleNamespace(state=SimpleNamespace(auth_service=service))

    result = await auth_router._call_auth_service(
        app,
        400,
        "verify_register_otp",
        "fresh@example.com",
        "123456",
    )

    assert result == {"temp_token": "temp-otp"}
    assert service.verify_otp_calls == [("fresh@example.com", "123456")]


@pytest.mark.asyncio
async def test_call_auth_service_maps_value_error_to_given_status():
    service = _FakeAuthService()
    service.complete_register_error = ValueError("邀请码无效")
    app = SimpleNamespace(state=SimpleNamespace(auth_service=service))

    with pytest.raises(HTTPException) as exc_info:
        await auth_router._call_auth_service(
            app,
            400,
            "complete_register",
            "temp-otp",
            "invite-1",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "邀请码无效"


@pytest.mark.asyncio
async def test_send_otp_uses_auth_router_helper(monkeypatch: pytest.MonkeyPatch):
    app = SimpleNamespace(state=SimpleNamespace(auth_service=_FakeAuthService()))
    calls: list[tuple[object, int, str, tuple[object, ...]]] = []

    async def _fake_call_auth_service(app_obj, status_code: int, method_name: str, *args: object):
        calls.append((app_obj, status_code, method_name, args))
        return None

    monkeypatch.setattr(auth_router, "_call_auth_service", _fake_call_auth_service)

    result = await auth_router.send_otp(
        auth_router.SendOtpRequest(email="fresh@example.com", password="pass1234", invite_code="invite-1"),
        app,
    )

    assert result == {"ok": True}
    assert calls == [
        (
            app,
            400,
            "send_otp",
            ("fresh@example.com", "pass1234", "invite-1"),
        )
    ]


@pytest.mark.asyncio
async def test_login_uses_auth_router_helper(monkeypatch: pytest.MonkeyPatch):
    app = SimpleNamespace(state=SimpleNamespace(auth_service=_FakeAuthService()))
    calls: list[tuple[object, int, str, tuple[object, ...]]] = []

    async def _fake_call_auth_service(app_obj, status_code: int, method_name: str, *args: object):
        calls.append((app_obj, status_code, method_name, args))
        return {"token": "tok-helper"}

    monkeypatch.setattr(auth_router, "_call_auth_service", _fake_call_auth_service)

    result = await auth_router.login(
        auth_router.LoginRequest(identifier="fresh@example.com", password="pass1234"),
        app,
    )

    assert result == {"token": "tok-helper"}
    assert calls == [
        (
            app,
            401,
            "login",
            ("fresh@example.com", "pass1234"),
        )
    ]


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
