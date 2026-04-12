from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.web.core.dependencies import get_app, get_current_user_id
from backend.web.routers import messaging as messaging_router
from backend.web.utils.serializers import avatar_url
from storage.contracts import ContactEdgeRow


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


def _empty_contact_repo() -> SimpleNamespace:
    return SimpleNamespace(get=lambda _owner_id, _target_id: None, list_for_user=lambda _owner_id: [])


def _contact_repo(active_pairs: set[tuple[str, str]] | None = None) -> SimpleNamespace:
    active_pairs = active_pairs or set()

    def get(owner_id: str, target_id: str):
        if (owner_id, target_id) not in active_pairs:
            return None
        return ContactEdgeRow(
            source_user_id=owner_id,
            target_user_id=target_id,
            kind="normal",
            state="active",
            created_at=1.0,
        )

    return SimpleNamespace(
        get=get,
        list_for_user=lambda owner_id: [get(owner_id, target_id) for source_id, target_id in active_pairs if source_id == owner_id],
    )


def _create_chat_route_state(
    *,
    users: dict[str, SimpleNamespace] | None = None,
    thread_user_ids: set[str] | None = None,
    relationship_state: str | dict[str, str] = "visit",
    active_contact_pairs: set[tuple[str, str]] | None = None,
    group_route: bool = True,
) -> tuple[SimpleNamespace, list[tuple[list[str], str | None]]]:
    called: list[tuple[list[str], str | None]] = []
    users = users or {}
    thread_user_ids = thread_user_ids or set()

    def chat_factory(user_ids: list[str], title: str | None):
        called.append((user_ids, title))
        return {"id": "chat-1", "title": title, "status": "active", "created_at": 0}

    def get_state(_viewer: str, participant: str) -> str:
        return relationship_state.get(participant, "none") if isinstance(relationship_state, dict) else relationship_state

    messaging_entrypoint = {"create_group_chat" if group_route else "find_or_create_chat": chat_factory}
    state = SimpleNamespace(
        user_repo=SimpleNamespace(get_by_id=lambda uid: users.get(uid)),
        thread_repo=SimpleNamespace(
            get_by_user_id=lambda uid: {"id": f"thread-{uid}"} if uid in thread_user_ids else None,
        ),
        relationship_service=SimpleNamespace(get_state=get_state),
        contact_repo=_contact_repo(active_contact_pairs),
        messaging_service=SimpleNamespace(**messaging_entrypoint),
    )
    return state, called


def test_messaging_crud_routes_are_sync_threadpool_boundaries() -> None:
    sync_routes = [
        messaging_router.list_chats,
        messaging_router.create_chat,
        messaging_router.get_chat,
        messaging_router.list_messages,
        messaging_router.send_message,
        messaging_router.retract_message,
        messaging_router.delete_message_for_self,
        messaging_router.mark_read,
        messaging_router.delete_chat,
        messaging_router.mute_chat,
    ]

    assert [fn.__name__ for fn in sync_routes if inspect.iscoroutinefunction(fn)] == []
    assert inspect.iscoroutinefunction(messaging_router.stream_chat_events)


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


def test_get_chat_uses_access_helper(monkeypatch: pytest.MonkeyPatch):
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

    result = messaging_router.get_chat("chat-1", user_id="user-1", app=app)

    assert result == {
        "id": "chat-1",
        "title": "Chat title",
        "status": "active",
        "created_at": "2026-04-07T00:00:00Z",
        "entities": [],
    }
    assert seen == [("helper", (app, "chat-1", "user-1"))]


def test_delete_chat_uses_access_helper(monkeypatch: pytest.MonkeyPatch):
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

    result = messaging_router.delete_chat("chat-1", user_id="user-1", app=app)

    assert result == {"status": "deleted"}
    assert seen == [
        ("helper", (app, "chat-1", "user-1")),
        ("delete", "chat-1"),
    ]


def test_get_chat_resolves_thread_user_participant_via_thread_repo(monkeypatch: pytest.MonkeyPatch):
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

    result = messaging_router.get_chat("chat-1", user_id="human-user-1", app=app)

    assert result["entities"] == [
        {
            "id": "thread-user-1",
            "name": "Toad",
            "type": "agent",
            "avatar_url": avatar_url("agent-user-1", False),
        }
    ]


def test_list_messages_resolves_thread_user_sender_name_via_thread_repo():
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

    result = messaging_router.list_messages("chat-1", user_id="human-user-1", app=app)

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


def test_send_message_consumes_service_owned_message_projection() -> None:
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

    result = messaging_router.send_message(
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


def test_send_message_accepts_owned_thread_user_sender_id_via_thread_repo():
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

    result = messaging_router.send_message(
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


def test_create_chat_rejects_template_member_ids_for_group_participants() -> None:
    state, called = _create_chat_route_state(
        users={
            "agent-user-1": SimpleNamespace(id="agent-user-1", type="agent", owner_user_id="owner-user-1"),
            "agent-user-2": SimpleNamespace(id="agent-user-2", type="agent", owner_user_id="owner-user-1"),
        },
        thread_user_ids={"owned-agent-1"},
    )
    app = SimpleNamespace(state=state)

    with pytest.raises(HTTPException) as exc_info:
        messaging_router.create_chat(
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


def test_create_chat_rejects_template_member_id_for_direct_participant() -> None:
    state, called = _create_chat_route_state(
        users={"agent-user-1": SimpleNamespace(id="agent-user-1", type="agent", owner_user_id="owner-user-1")},
        thread_user_ids={"owned-agent-1"},
        group_route=False,
    )
    app = SimpleNamespace(state=state)

    with pytest.raises(HTTPException) as exc_info:
        messaging_router.create_chat(
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


def test_create_chat_accepts_human_and_thread_social_user_ids_for_group_participants() -> None:
    state, called = _create_chat_route_state(thread_user_ids={"thread-user-1", "thread-user-2"})
    app = SimpleNamespace(state=state)

    result = messaging_router.create_chat(
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


def test_create_group_chat_rejects_external_participant_without_active_relationship() -> None:
    state, called = _create_chat_route_state(
        users={
            "owned-agent-1": SimpleNamespace(id="owned-agent-1", owner_user_id="human-user-1"),
            "human-user-2": SimpleNamespace(id="human-user-2", owner_user_id=None),
        },
        thread_user_ids={"owned-agent-1"},
        relationship_state="pending",
    )
    app = SimpleNamespace(state=state)

    with pytest.raises(HTTPException) as exc_info:
        messaging_router.create_chat(
            messaging_router.CreateChatBody(
                user_ids=["human-user-1", "owned-agent-1", "human-user-2"],
                title="bad-group",
            ),
            user_id="human-user-1",
            app=app,
        )

    assert exc_info.value.status_code == 400
    assert "relationship" in str(exc_info.value.detail).lower()
    assert called == []


def test_create_group_chat_accepts_external_active_contact_without_relationship() -> None:
    state, called = _create_chat_route_state(
        users={
            "owned-agent-1": SimpleNamespace(id="owned-agent-1", owner_user_id="human-user-1"),
            "human-user-2": SimpleNamespace(id="human-user-2", owner_user_id=None),
        },
        thread_user_ids={"owned-agent-1"},
        relationship_state="none",
        active_contact_pairs={("human-user-1", "human-user-2")},
    )
    app = SimpleNamespace(state=state)

    result = messaging_router.create_chat(
        messaging_router.CreateChatBody(
            user_ids=["human-user-1", "owned-agent-1", "human-user-2"],
            title="contact-group",
        ),
        user_id="human-user-1",
        app=app,
    )

    assert called == [(["human-user-1", "owned-agent-1", "human-user-2"], "contact-group")]
    assert result["id"] == "chat-1"


def test_create_group_chat_accepts_agent_owned_by_external_active_contact() -> None:
    state, called = _create_chat_route_state(
        users={
            "owned-agent-1": SimpleNamespace(id="owned-agent-1", owner_user_id="human-user-1"),
            "external-agent-1": SimpleNamespace(id="external-agent-1", owner_user_id="human-user-2"),
            "human-user-2": SimpleNamespace(id="human-user-2", owner_user_id=None),
        },
        thread_user_ids={"owned-agent-1", "external-agent-1"},
        relationship_state="none",
        active_contact_pairs={("human-user-1", "human-user-2")},
    )
    app = SimpleNamespace(state=state)

    result = messaging_router.create_chat(
        messaging_router.CreateChatBody(
            user_ids=["human-user-1", "owned-agent-1", "external-agent-1"],
            title="owner-contact-agent-group",
        ),
        user_id="human-user-1",
        app=app,
    )

    assert called == [(["human-user-1", "owned-agent-1", "external-agent-1"], "owner-contact-agent-group")]
    assert result["id"] == "chat-1"


def test_create_group_chat_accepts_owned_agent_without_relationship() -> None:
    state, called = _create_chat_route_state(
        users={
            "owned-agent-1": SimpleNamespace(id="owned-agent-1", owner_user_id="human-user-1"),
            "human-user-2": SimpleNamespace(id="human-user-2", owner_user_id=None),
        },
        thread_user_ids={"owned-agent-1"},
        relationship_state={"human-user-2": "visit"},
    )
    app = SimpleNamespace(state=state)

    result = messaging_router.create_chat(
        messaging_router.CreateChatBody(
            user_ids=["human-user-1", "owned-agent-1", "human-user-2"],
            title="good-group",
        ),
        user_id="human-user-1",
        app=app,
    )

    assert called == [(["human-user-1", "owned-agent-1", "human-user-2"], "good-group")]
    assert result["id"] == "chat-1"


def test_create_chat_rejects_unknown_participant_ids_instead_of_falling_to_storage_fk() -> None:
    state, called = _create_chat_route_state()
    app = SimpleNamespace(state=state)

    with pytest.raises(HTTPException) as exc_info:
        messaging_router.create_chat(
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
