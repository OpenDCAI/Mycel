from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.routers import messaging as messaging_router
from backend.web.utils.serializers import avatar_url


def _chat(chat_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=chat_id,
        title="Chat title",
        status="active",
        created_at="2026-04-07T00:00:00Z",
    )


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
            messaging_service=SimpleNamespace(list_chat_members=lambda _chat_id: []),
            member_repo=SimpleNamespace(get_by_id=lambda _member_id: None),
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
                list_chat_members=lambda _chat_id: [
                    {"user_id": "human-user-1"},
                    {"user_id": "thread-user-1"},
                ]
            ),
            member_repo=SimpleNamespace(
                get_by_id=lambda uid: (
                    None
                    if uid == "thread-user-1"
                    else SimpleNamespace(id=uid, name="Toad", type="mycel_agent", avatar=None)
                    if uid == "member-agent-1"
                    else None
                )
            ),
            thread_repo=SimpleNamespace(
                get_by_user_id=lambda uid: {"id": "thread-1", "member_id": "member-agent-1"} if uid == "thread-user-1" else None
            ),
        )
    )

    result = await messaging_router.get_chat("chat-1", user_id="human-user-1", app=app)

    assert result["entities"] == [
        {
            "id": "member-agent-1",
            "name": "Toad",
            "type": "mycel_agent",
            "avatar_url": avatar_url("member-agent-1", False),
        }
    ]


@pytest.mark.asyncio
async def test_list_messages_resolves_thread_user_sender_name_via_thread_repo():
    app = SimpleNamespace(
        state=SimpleNamespace(
            messaging_service=SimpleNamespace(
                is_chat_member=lambda _chat_id, _user_id: True,
                list_messages=lambda _chat_id, **_kwargs: [
                    {
                        "id": "msg-1",
                        "chat_id": "chat-1",
                        "sender_id": "thread-user-1",
                        "content": "hello",
                        "message_type": "human",
                        "created_at": "2026-04-07T00:00:00Z",
                    }
                ],
            ),
            member_repo=SimpleNamespace(
                get_by_id=lambda uid: (
                    None
                    if uid == "thread-user-1"
                    else SimpleNamespace(id=uid, name="Toad", type="mycel_agent", avatar=None)
                    if uid == "member-agent-1"
                    else None
                )
            ),
            thread_repo=SimpleNamespace(
                get_by_user_id=lambda uid: {"id": "thread-1", "member_id": "member-agent-1"} if uid == "thread-user-1" else None
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
