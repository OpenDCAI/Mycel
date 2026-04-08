from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.web.core.dependencies import get_app, get_current_user_id
from backend.web.routers import messaging as messaging_router
from backend.web.utils.serializers import avatar_url


def _chat(chat_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=chat_id,
        title="Chat title",
        status="active",
        created_at="2026-04-07T00:00:00Z",
    )


def _route_test_app(state: SimpleNamespace) -> FastAPI:
    app = FastAPI()
    app.state = state
    app.include_router(messaging_router.router)
    app.dependency_overrides[get_current_user_id] = lambda: "human-user-1"
    app.dependency_overrides[get_app] = lambda: app
    return app


def test_get_accessible_chat_or_404_returns_chat():
    chat = _chat("chat-1")
    app = SimpleNamespace(
        state=SimpleNamespace(
            chat_repo=SimpleNamespace(get_by_id=lambda chat_id: chat if chat_id == "chat-1" else None),
            messaging_service=SimpleNamespace(is_chat_member=lambda chat_id, user_id: (chat_id, user_id) == ("chat-1", "user-1")),
        )
    )

    result = messaging_router._get_accessible_chat_or_404(app, "chat-1", "user-1")

    assert result is chat


def test_get_accessible_chat_or_404_raises_404_for_missing_chat():
    app = SimpleNamespace(
        state=SimpleNamespace(
            chat_repo=SimpleNamespace(get_by_id=lambda _chat_id: None),
            messaging_service=SimpleNamespace(is_chat_member=lambda _chat_id, _user_id: True),
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        messaging_router._get_accessible_chat_or_404(app, "missing", "user-1")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Chat not found"


def test_get_accessible_chat_or_404_raises_403_for_non_member():
    app = SimpleNamespace(
        state=SimpleNamespace(
            chat_repo=SimpleNamespace(get_by_id=lambda _chat_id: _chat("chat-1")),
            messaging_service=SimpleNamespace(is_chat_member=lambda _chat_id, _user_id: False),
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        messaging_router._get_accessible_chat_or_404(app, "chat-1", "user-2")

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Not a participant of this chat"


def test_resolve_display_user_delegates_to_messaging_service(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, str]] = []
    expected = SimpleNamespace(id="agent-user-1", display_name="Toad")

    app = SimpleNamespace(
        state=SimpleNamespace(
            messaging_service=SimpleNamespace(
                resolve_display_user=lambda social_user_id: seen.append(("resolve_display_user", social_user_id)) or expected
            ),
            user_repo=SimpleNamespace(name="user-repo"),
            thread_repo=SimpleNamespace(name="thread-repo"),
        )
    )

    result = messaging_router._resolve_display_user(app, "thread-user-1")

    assert result is expected
    assert seen == [("resolve_display_user", "thread-user-1")]


@pytest.mark.asyncio
async def test_get_chat_uses_access_helper(monkeypatch: pytest.MonkeyPatch):
    seen: list[tuple[str, object]] = []
    chat = _chat("chat-1")

    def fake_helper(app_obj, chat_id: str, user_id: str):
        seen.append(("helper", (app_obj, chat_id, user_id)))
        return chat

    monkeypatch.setattr(messaging_router, "_get_accessible_chat_or_404", fake_helper)

    app = SimpleNamespace(
        state=SimpleNamespace(
            chat_repo=SimpleNamespace(
                get_by_id=lambda _chat_id: (_ for _ in ()).throw(AssertionError("route should use helper, not chat_repo lookup directly"))
            ),
            messaging_service=SimpleNamespace(
                get_chat_detail=lambda chat_obj: {
                    "id": chat_obj.id,
                    "title": chat_obj.title,
                    "status": chat_obj.status,
                    "created_at": chat_obj.created_at,
                    "entities": [],
                },
                list_chat_members=lambda _chat_id: (_ for _ in ()).throw(
                    AssertionError("route should consume service-owned chat detail, not rebuild members locally")
                ),
            ),
            user_repo=SimpleNamespace(get_by_id=lambda _user_id: None),
        )
    )

    result = await messaging_router.get_chat("chat-1", user_id="user-1", app=app)

    assert result == {
        "id": "chat-1",
        "title": "Chat title",
        "status": "active",
        "created_at": "2026-04-07T00:00:00Z",
        "entities": [],
    }
    assert seen == [("helper", (app, "chat-1", "user-1"))]


@pytest.mark.asyncio
async def test_delete_chat_uses_access_helper(monkeypatch: pytest.MonkeyPatch):
    seen: list[tuple[str, object]] = []
    chat = _chat("chat-1")

    def fake_helper(app_obj, chat_id: str, user_id: str):
        seen.append(("helper", (app_obj, chat_id, user_id)))
        return chat

    monkeypatch.setattr(messaging_router, "_get_accessible_chat_or_404", fake_helper)

    app = SimpleNamespace(
        state=SimpleNamespace(
            chat_repo=SimpleNamespace(
                get_by_id=lambda _chat_id: (_ for _ in ()).throw(AssertionError("route should use helper, not chat_repo lookup directly")),
                delete=lambda chat_id: seen.append(("delete", chat_id)),
            ),
        )
    )

    result = await messaging_router.delete_chat("chat-1", user_id="user-1", app=app)

    assert result == {"status": "deleted"}
    assert seen == [
        ("helper", (app, "chat-1", "user-1")),
        ("delete", "chat-1"),
    ]


@pytest.mark.asyncio
async def test_get_chat_resolves_thread_user_participant_via_thread_repo(monkeypatch: pytest.MonkeyPatch):
    chat = _chat("chat-1")

    monkeypatch.setattr(messaging_router, "_get_accessible_chat_or_404", lambda _app, _chat_id, _user_id: chat)

    app = SimpleNamespace(
        state=SimpleNamespace(
            messaging_service=SimpleNamespace(
                get_chat_detail=lambda _chat: {
                    "id": "chat-1",
                    "title": "Chat title",
                    "status": "active",
                    "created_at": "2026-04-07T00:00:00Z",
                    "entities": [
                        {
                            "id": "thread-user-1",
                            "name": "Toad",
                            "type": "agent",
                            "avatar_url": avatar_url("agent-user-1", False),
                        }
                    ],
                }
            ),
            user_repo=SimpleNamespace(
                get_by_id=lambda uid: (
                    None
                    if uid == "thread-user-1"
                    else SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None)
                    if uid == "agent-user-1"
                    else None
                )
            ),
            thread_repo=SimpleNamespace(
                get_by_user_id=lambda uid: {"id": "thread-1", "agent_user_id": "agent-user-1"} if uid == "thread-user-1" else None
            ),
        )
    )

    result = await messaging_router.get_chat("chat-1", user_id="human-user-1", app=app)

    assert result["entities"] == [
        {
            "id": "thread-user-1",
            "name": "Toad",
            "type": "agent",
            "avatar_url": avatar_url("agent-user-1", False),
        }
    ]


@pytest.mark.asyncio
async def test_list_messages_resolves_thread_user_sender_name_via_thread_repo():
    app = SimpleNamespace(
        state=SimpleNamespace(
            messaging_service=SimpleNamespace(
                is_chat_member=lambda _chat_id, _user_id: True,
                list_message_responses=lambda _chat_id, **_kwargs: [
                    {
                        "id": "msg-1",
                        "chat_id": "chat-1",
                        "sender_id": "thread-user-1",
                        "sender_name": "Toad",
                        "content": "hello",
                        "message_type": "human",
                        "mentioned_ids": [],
                        "signal": None,
                        "retracted_at": None,
                        "created_at": "2026-04-07T00:00:00Z",
                    }
                ],
                resolve_display_user=lambda uid: (
                    SimpleNamespace(id="agent-user-1", display_name="Toad", type="agent", avatar=None)
                    if uid == "thread-user-1"
                    else SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None)
                    if uid == "agent-user-1"
                    else None
                ),
            ),
            user_repo=SimpleNamespace(
                get_by_id=lambda uid: (
                    None
                    if uid == "thread-user-1"
                    else SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None)
                    if uid == "agent-user-1"
                    else None
                )
            ),
            thread_repo=SimpleNamespace(
                get_by_user_id=lambda uid: {"id": "thread-1", "agent_user_id": "agent-user-1"} if uid == "thread-user-1" else None
            ),
        )
    )

    result = await messaging_router.list_messages("chat-1", user_id="human-user-1", app=app)

    assert result == [
        {
            "id": "msg-1",
            "chat_id": "chat-1",
            "sender_id": "thread-user-1",
            "sender_name": "Toad",
            "content": "hello",
            "message_type": "human",
            "mentioned_ids": [],
            "signal": None,
            "retracted_at": None,
            "created_at": "2026-04-07T00:00:00Z",
        }
    ]


def test_list_messages_route_resolves_sender_name_via_messaging_service() -> None:
    test_app = _route_test_app(
        SimpleNamespace(
            messaging_service=SimpleNamespace(
                is_chat_member=lambda _chat_id, _user_id: True,
                list_message_responses=lambda _chat_id, **_kwargs: [
                    {
                        "id": "msg-1",
                        "chat_id": "chat-1",
                        "sender_id": "thread-user-1",
                        "sender_name": "Projected Toad",
                        "content": "hello",
                        "message_type": "human",
                        "mentioned_ids": [],
                        "signal": None,
                        "retracted_at": None,
                        "created_at": "2026-04-07T00:00:00Z",
                    }
                ],
                list_messages=lambda _chat_id, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("route should consume service-owned message projection")
                ),
            )
        )
    )

    try:
        with TestClient(test_app) as client:
            response = client.get("/api/chats/chat-1/messages")
    finally:
        test_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "msg-1",
            "chat_id": "chat-1",
            "sender_id": "thread-user-1",
            "sender_name": "Projected Toad",
            "content": "hello",
            "message_type": "human",
            "mentioned_ids": [],
            "signal": None,
            "retracted_at": None,
            "created_at": "2026-04-07T00:00:00Z",
        }
    ]


@pytest.mark.asyncio
async def test_send_message_consumes_service_owned_message_projection() -> None:
    seen: list[tuple[str, str, str]] = []
    app = SimpleNamespace(
        state=SimpleNamespace(
            messaging_service=SimpleNamespace(
                resolve_display_user=lambda uid: (
                    SimpleNamespace(
                        id="agent-user-1",
                        display_name="Ownership Toad",
                        type="agent",
                        avatar=None,
                        owner_user_id="owner-user-1",
                    )
                    if uid == "thread-user-1"
                    else None
                ),
                send=lambda chat_id, sender_id, content, **_kwargs: (
                    seen.append((chat_id, sender_id, content))
                    or {
                        "id": "msg-1",
                        "chat_id": chat_id,
                        "sender_id": sender_id,
                        "content": content,
                        "message_type": "human",
                        "created_at": "2026-04-07T00:00:00Z",
                    }
                ),
                project_message_response=lambda msg: {
                    "id": msg["id"],
                    "chat_id": msg["chat_id"],
                    "sender_id": msg["sender_id"],
                    "sender_name": "Projected Toad",
                    "content": msg["content"],
                    "message_type": msg["message_type"],
                    "mentioned_ids": [],
                    "signal": None,
                    "retracted_at": None,
                    "created_at": msg["created_at"],
                },
            ),
        )
    )

    result = await messaging_router.send_message(
        "chat-1",
        messaging_router.SendMessageBody(content="hello", sender_id="thread-user-1"),
        user_id="owner-user-1",
        app=app,
    )

    assert seen == [("chat-1", "thread-user-1", "hello")]
    assert result == {
        "id": "msg-1",
        "chat_id": "chat-1",
        "sender_id": "thread-user-1",
        "sender_name": "Projected Toad",
        "content": "hello",
        "message_type": "human",
        "mentioned_ids": [],
        "signal": None,
        "retracted_at": None,
        "created_at": "2026-04-07T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_send_message_accepts_owned_thread_user_sender_id_via_thread_repo():
    seen: list[tuple[str, str, str]] = []
    app = SimpleNamespace(
        state=SimpleNamespace(
            user_repo=SimpleNamespace(
                get_by_id=lambda uid: (
                    None
                    if uid == "thread-user-1"
                    else SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None, owner_user_id="owner-user-1")
                    if uid == "agent-user-1"
                    else None
                )
            ),
            thread_repo=SimpleNamespace(
                get_by_user_id=lambda uid: {"id": "thread-1", "agent_user_id": "agent-user-1"} if uid == "thread-user-1" else None
            ),
            messaging_service=SimpleNamespace(
                resolve_display_user=lambda uid: (
                    SimpleNamespace(
                        id="agent-user-1",
                        display_name="Toad",
                        type="agent",
                        avatar=None,
                        owner_user_id="owner-user-1",
                    )
                    if uid == "thread-user-1"
                    else None
                ),
                send=lambda chat_id, sender_id, content, **_kwargs: (
                    seen.append((chat_id, sender_id, content))
                    or {
                        "id": "msg-1",
                        "chat_id": chat_id,
                        "sender_id": sender_id,
                        "content": content,
                        "message_type": "human",
                        "created_at": "2026-04-07T00:00:00Z",
                    }
                ),
                project_message_response=lambda msg: {
                    "id": msg["id"],
                    "chat_id": msg["chat_id"],
                    "sender_id": msg["sender_id"],
                    "sender_name": "Toad",
                    "content": msg["content"],
                    "message_type": msg["message_type"],
                    "mentioned_ids": [],
                    "signal": None,
                    "retracted_at": None,
                    "created_at": msg["created_at"],
                },
            ),
        )
    )

    result = await messaging_router.send_message(
        "chat-1",
        messaging_router.SendMessageBody(content="hello", sender_id="thread-user-1"),
        user_id="owner-user-1",
        app=app,
    )

    assert seen == [("chat-1", "thread-user-1", "hello")]
    assert result == {
        "id": "msg-1",
        "chat_id": "chat-1",
        "sender_id": "thread-user-1",
        "sender_name": "Toad",
        "content": "hello",
        "message_type": "human",
        "mentioned_ids": [],
        "signal": None,
        "retracted_at": None,
        "created_at": "2026-04-07T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_create_chat_rejects_template_member_ids_for_group_participants() -> None:
    called: list[tuple[list[str], str | None]] = []
    app = SimpleNamespace(
        state=SimpleNamespace(
            user_repo=SimpleNamespace(
                get_by_id=lambda uid: (
                    SimpleNamespace(id=uid, type="agent", owner_user_id="owner-user-1") if uid in {"agent-user-1", "agent-user-2"} else None
                )
            ),
            thread_repo=SimpleNamespace(get_by_user_id=lambda _uid: None),
            messaging_service=SimpleNamespace(
                create_group_chat=lambda user_ids, title: (
                    called.append((user_ids, title)) or {"id": "chat-1", "title": title, "status": "active", "created_at": 0}
                )
            ),
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await messaging_router.create_chat(
            messaging_router.CreateChatBody(
                user_ids=["human-user-1", "agent-user-1", "agent-user-2"],
                title="bad-group",
            ),
            user_id="human-user-1",
            app=app,
        )

    assert exc_info.value.status_code == 400
    assert "actor" in str(exc_info.value.detail).lower()
    assert called == []


@pytest.mark.asyncio
async def test_create_chat_rejects_template_member_id_for_direct_participant() -> None:
    called: list[tuple[list[str], str | None]] = []
    app = SimpleNamespace(
        state=SimpleNamespace(
            user_repo=SimpleNamespace(
                get_by_id=lambda uid: SimpleNamespace(id=uid, type="agent", owner_user_id="owner-user-1") if uid == "agent-user-1" else None
            ),
            thread_repo=SimpleNamespace(get_by_user_id=lambda _uid: None),
            messaging_service=SimpleNamespace(
                find_or_create_chat=lambda user_ids, title: (
                    called.append((user_ids, title)) or {"id": "chat-1", "title": title, "status": "active", "created_at": 0}
                )
            ),
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await messaging_router.create_chat(
            messaging_router.CreateChatBody(
                user_ids=["human-user-1", "agent-user-1"],
                title=None,
            ),
            user_id="human-user-1",
            app=app,
        )

    assert exc_info.value.status_code == 400
    assert "actor" in str(exc_info.value.detail).lower()
    assert called == []


@pytest.mark.asyncio
async def test_create_chat_accepts_human_and_thread_social_user_ids_for_group_participants() -> None:
    called: list[tuple[list[str], str | None]] = []
    app = SimpleNamespace(
        state=SimpleNamespace(
            user_repo=SimpleNamespace(get_by_id=lambda _uid: None),
            thread_repo=SimpleNamespace(
                get_by_user_id=lambda uid: (
                    {"id": f"thread-{uid}", "agent_user_id": "agent-user-1"} if uid in {"thread-user-1", "thread-user-2"} else None
                )
            ),
            messaging_service=SimpleNamespace(
                create_group_chat=lambda user_ids, title: (
                    called.append((user_ids, title)) or {"id": "chat-1", "title": title, "status": "active", "created_at": 0}
                )
            ),
        )
    )

    result = await messaging_router.create_chat(
        messaging_router.CreateChatBody(
            user_ids=["human-user-1", "thread-user-1", "thread-user-2"],
            title="good-group",
        ),
        user_id="human-user-1",
        app=app,
    )

    assert called == [(["human-user-1", "thread-user-1", "thread-user-2"], "good-group")]
    assert result == {
        "id": "chat-1",
        "title": "good-group",
        "status": "active",
        "created_at": 0,
    }


@pytest.mark.asyncio
async def test_create_chat_rejects_unknown_participant_ids_instead_of_falling_to_storage_fk() -> None:
    called: list[tuple[list[str], str | None]] = []
    app = SimpleNamespace(
        state=SimpleNamespace(
            user_repo=SimpleNamespace(get_by_id=lambda _uid: None),
            thread_repo=SimpleNamespace(get_by_user_id=lambda _uid: None),
            messaging_service=SimpleNamespace(
                create_group_chat=lambda user_ids, title: (
                    called.append((user_ids, title)) or {"id": "chat-1", "title": title, "status": "active", "created_at": 0}
                )
            ),
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await messaging_router.create_chat(
            messaging_router.CreateChatBody(
                user_ids=["human-user-1", "thread-id-not-a-user", "thread-user-2"],
                title="bad-group",
            ),
            user_id="human-user-1",
            app=app,
        )

    assert exc_info.value.status_code == 400
    assert "participant" in str(exc_info.value.detail).lower()
    assert called == []
