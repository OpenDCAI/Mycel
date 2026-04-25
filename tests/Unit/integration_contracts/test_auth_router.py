from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.chat.api.http import chats_router
from backend.identity.auth.service import ExternalUserAlreadyExistsError
from backend.web.routers import auth as auth_router


class _FakeAuthService:
    def __init__(self) -> None:
        self.send_otp_calls: list[tuple[str, str, str]] = []
        self.login_calls: list[tuple[str, str]] = []
        self.create_external_user_token_calls: list[tuple[str, str, str]] = []
        self.login_result = {"token": "tok-login"}
        self.create_external_user_token_result = {
            "token": "tok-external",
            "user": {"id": "external-1", "name": "Codex Local", "type": "external"},
        }
        self.send_otp_error: Exception | None = None
        self.login_error: Exception | None = None
        self.create_external_user_token_error: Exception | None = None

    def send_otp(self, email: str, password: str, invite_code: str) -> None:
        self.send_otp_calls.append((email, password, invite_code))
        if self.send_otp_error is not None:
            raise self.send_otp_error

    def login(self, identifier: str, password: str) -> dict:
        self.login_calls.append((identifier, password))
        if self.login_error is not None:
            raise self.login_error
        return self.login_result

    def create_external_user_token(self, user_id: str, display_name: str, *, created_by_user_id: str) -> dict:
        self.create_external_user_token_calls.append((user_id, display_name, created_by_user_id))
        if self.create_external_user_token_error is not None:
            raise self.create_external_user_token_error
        return self.create_external_user_token_result


@pytest.mark.asyncio
async def test_send_otp_calls_auth_service_directly():
    service = _FakeAuthService()
    app = SimpleNamespace(state=SimpleNamespace(auth_runtime_state=SimpleNamespace(auth_service=service)))

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
    app = SimpleNamespace(state=SimpleNamespace(auth_runtime_state=SimpleNamespace(auth_service=service)))

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
    app = SimpleNamespace(state=SimpleNamespace(auth_runtime_state=SimpleNamespace(auth_service=service)))

    with pytest.raises(HTTPException) as exc_info:
        await auth_router.login(auth_router.LoginRequest(identifier="fresh@example.com", password="pass1234"), app)

    assert exc_info.value.status_code == 401
    assert "Invalid username or password" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_create_external_user_calls_auth_service_with_current_user():
    service = _FakeAuthService()
    app = SimpleNamespace(state=SimpleNamespace(auth_runtime_state=SimpleNamespace(auth_service=service)))

    result = await auth_router.create_external_user(
        auth_router.CreateExternalUserRequest(user_id="external-1", display_name="Codex Local"),
        app,
        current_user_id="owner-1",
    )

    assert result == service.create_external_user_token_result
    assert service.create_external_user_token_calls == [("external-1", "Codex Local", "owner-1")]


@pytest.mark.asyncio
async def test_auth_me_returns_authenticated_user_identity():
    result = await auth_router.me(
        SimpleNamespace(
            id="external-1",
            display_name="Codex Local",
            type=SimpleNamespace(value="external"),
            email=None,
            mycel_id=None,
            avatar=None,
        )
    )

    assert result == {
        "id": "external-1",
        "name": "Codex Local",
        "type": "external",
        "email": None,
        "mycel_id": None,
        "avatar": None,
    }


@pytest.mark.asyncio
async def test_create_external_user_maps_duplicate_to_conflict():
    service = _FakeAuthService()
    service.create_external_user_token_error = ExternalUserAlreadyExistsError("external user already exists: external-1")
    app = SimpleNamespace(state=SimpleNamespace(auth_runtime_state=SimpleNamespace(auth_service=service)))

    with pytest.raises(HTTPException) as exc_info:
        await auth_router.create_external_user(
            auth_router.CreateExternalUserRequest(user_id="external-1", display_name="Codex Local"),
            app,
            current_user_id="owner-1",
        )

    assert exc_info.value.status_code == 409
    assert "already exists" in str(exc_info.value.detail)


def test_create_external_user_route_requires_current_user_dependency():
    service = _FakeAuthService()
    app = FastAPI()
    app.state.auth_runtime_state = SimpleNamespace(auth_service=service)
    app.include_router(auth_router.router)

    with TestClient(app) as client:
        response = client.post("/api/auth/external-users", json={"user_id": "external-1", "display_name": "Codex Local"})

    assert response.status_code == 401
    assert service.create_external_user_token_calls == []


def test_create_external_user_openapi_is_public_auth_surface():
    app = FastAPI()
    app.include_router(auth_router.router)

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/auth/external-users" in paths
    assert not [path for path in paths if path.startswith("/api/" + "internal")]


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
    runtime_state = SimpleNamespace(
        chat_repo=SimpleNamespace(get_by_id=lambda _chat_id: {"id": "chat-1"}),
        messaging_service=SimpleNamespace(is_chat_member=lambda _chat_id, _user_id: False),
        chat_event_bus=_ChatEventBus(),
    )
    app = SimpleNamespace(state=SimpleNamespace(chat_runtime_state=runtime_state))

    with pytest.raises(HTTPException) as exc_info:
        await chats_router.stream_chat_events(
            "chat-1",
            user_id="user-1",
            chat_repo=app.state.chat_runtime_state.chat_repo,
            messaging_service=app.state.chat_runtime_state.messaging_service,
            chat_event_bus=app.state.chat_runtime_state.chat_event_bus,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Not a participant of this chat"


@pytest.mark.asyncio
async def test_chat_events_uses_authenticated_participant():
    event_bus = _ChatEventBus()
    runtime_state = SimpleNamespace(
        chat_repo=SimpleNamespace(get_by_id=lambda _chat_id: {"id": "chat-1"}),
        messaging_service=SimpleNamespace(is_chat_member=lambda _chat_id, user_id: user_id == "user-1"),
        chat_event_bus=event_bus,
    )
    app = SimpleNamespace(state=SimpleNamespace(chat_runtime_state=runtime_state))

    response = await chats_router.stream_chat_events(
        "chat-1",
        user_id="user-1",
        chat_repo=app.state.chat_runtime_state.chat_repo,
        messaging_service=app.state.chat_runtime_state.messaging_service,
        chat_event_bus=app.state.chat_runtime_state.chat_event_bus,
    )

    assert event_bus.subscribed == ["chat-1"]
    assert response.media_type == "text/event-stream"
