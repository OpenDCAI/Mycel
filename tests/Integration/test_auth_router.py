from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.routers import auth as auth_router
from backend.web.routers import messaging as chats_router


class _FakeAuthService:
    def __init__(self) -> None:
        self.send_otp_calls: list[tuple[str, str, str]] = []
        self.login_calls: list[tuple[str, str]] = []
        self.login_result = {"token": "tok-login"}
        self.send_otp_error: Exception | None = None
        self.login_error: Exception | None = None

    def send_otp(self, email: str, password: str, invite_code: str) -> None:
        self.send_otp_calls.append((email, password, invite_code))
        if self.send_otp_error is not None:
            raise self.send_otp_error

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
async def test_login_maps_value_error_to_unauthorized():
    service = _FakeAuthService()
    service.login_error = ValueError("Invalid username or password")
    app = SimpleNamespace(state=SimpleNamespace(auth_service=service))

    with pytest.raises(HTTPException) as exc_info:
        await auth_router.login(auth_router.LoginRequest(identifier="fresh@example.com", password="pass1234"), app)

    assert exc_info.value.status_code == 401
    assert "Invalid username or password" in str(exc_info.value.detail)


class _ChatEventBus:
    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.unsubscribed: list[tuple[str, object]] = []

    def subscribe(self, chat_id: str) -> object:
        self.subscribed.append(chat_id)
        return object()

    def unsubscribe(self, chat_id: str, queue: object) -> None:
        self.unsubscribed.append((chat_id, queue))


@pytest.mark.asyncio
async def test_chat_events_requires_chat_membership():
    app = SimpleNamespace(
        state=SimpleNamespace(
            chat_repo=SimpleNamespace(get_by_id=lambda _chat_id: {"id": "chat-1"}),
            messaging_service=SimpleNamespace(is_chat_member=lambda _chat_id, _user_id: False),
            chat_event_bus=_ChatEventBus(),
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await chats_router.stream_chat_events("chat-1", user_id="user-1", app=app)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Not a participant of this chat"


@pytest.mark.asyncio
async def test_chat_events_uses_authenticated_participant():
    event_bus = _ChatEventBus()
    app = SimpleNamespace(
        state=SimpleNamespace(
            chat_repo=SimpleNamespace(get_by_id=lambda _chat_id: {"id": "chat-1"}),
            messaging_service=SimpleNamespace(is_chat_member=lambda _chat_id, user_id: user_id == "user-1"),
            chat_event_bus=event_bus,
        )
    )

    response = await chats_router.stream_chat_events("chat-1", user_id="user-1", app=app)

    assert event_bus.subscribed == ["chat-1"]
    assert response.media_type == "text/event-stream"
