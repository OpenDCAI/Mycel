from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.routers import messaging as messaging_router


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
