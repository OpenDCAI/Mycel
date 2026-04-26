from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.chat.api.http import chats_router, relationships_router
from backend.identity.avatar.urls import avatar_url
from backend.web.core.dependencies import get_current_user_id
from storage.contracts import ContactEdgeRow


def _chat(chat_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=chat_id,
        type="group",
        title="Chat title",
        status="active",
        created_at="2026-04-07T00:00:00Z",
    )


def _route_test_app(state: SimpleNamespace) -> FastAPI:
    app = FastAPI()
    app.state = state
    app.include_router(chats_router.router)
    app.dependency_overrides[get_current_user_id] = lambda: "human-user-1"
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
    relationship_service = SimpleNamespace(get_state=get_state)
    contact_repo = _contact_repo(active_contact_pairs)
    messaging_service = SimpleNamespace(**messaging_entrypoint)
    state = SimpleNamespace(
        user_repo=SimpleNamespace(get_by_id=lambda uid: users.get(uid)),
        thread_repo=SimpleNamespace(
            get_by_user_id=lambda uid: {"id": f"thread-{uid}"} if uid in thread_user_ids else None,
        ),
        chat_runtime_state=SimpleNamespace(
            relationship_service=relationship_service,
            contact_repo=contact_repo,
            messaging_service=messaging_service,
        ),
    )
    return state, called


def _create_chat(app: SimpleNamespace, body: chats_router.CreateChatBody, *, user_id: str = "human-user-1"):
    return chats_router.create_chat(
        body,
        user_id=user_id,
        messaging_service=app.state.chat_runtime_state.messaging_service,
        user_repo=app.state.user_repo,
        thread_repo=app.state.thread_repo,
    )


def test_messaging_crud_routes_are_sync_threadpool_boundaries() -> None:
    sync_routes = [
        chats_router.list_chats,
        chats_router.create_chat,
        chats_router.get_chat,
        chats_router.list_messages,
        chats_router.send_message,
        chats_router.retract_message,
        chats_router.delete_message_for_self,
        chats_router.mark_read,
        chats_router.delete_chat,
        chats_router.mute_chat,
    ]

    assert [fn.__name__ for fn in sync_routes if inspect.iscoroutinefunction(fn)] == []


def test_relationship_bodies_do_not_accept_identity_fields() -> None:
    request_body = relationships_router.RelationshipRequestBody(target_user_id="user-2")
    action_body = relationships_router.RelationshipActionBody()

    assert request_body.target_user_id == "user-2"
    assert action_body.model_dump() == {}
    with pytest.raises(ValidationError):
        relationships_router.RelationshipRequestBody.model_validate({"target_user_id": "user-2", "requester_user_id": "user-1"})
    with pytest.raises(ValidationError):
        relationships_router.RelationshipActionBody.model_validate({"requester_user_id": "user-1"})
    with pytest.raises(ValidationError):
        relationships_router.RelationshipRequestBody.model_validate({"target_user_id": "user-2", "actor_" + "user_id": "user-1"})


def test_chat_join_request_bodies_do_not_accept_identity_fields() -> None:
    request_body = chats_router.ChatJoinRequestBody(message="please add me")
    action_body = chats_router.ChatJoinRequestActionBody()

    assert request_body.message == "please add me"
    assert action_body.model_dump() == {}
    with pytest.raises(ValidationError):
        chats_router.ChatJoinRequestBody.model_validate({"message": "please add me", "requester_user_id": "user-1"})
    with pytest.raises(ValidationError):
        chats_router.ChatJoinRequestActionBody.model_validate({"requester_user_id": "user-1"})
    with pytest.raises(ValidationError):
        chats_router.ChatJoinRequestBody.model_validate({"message": "please add me", "actor_" + "user_id": "user-1"})


def test_request_chat_join_uses_current_token_user() -> None:
    seen: list[tuple[str, str, str | None]] = []
    expected = {
        "id": "join-request-1",
        "chat_id": "chat-1",
        "requester_user_id": "human-user-2",
        "state": "pending",
        "message": "please add me",
        "created_at": 123.0,
        "updated_at": 123.0,
    }
    chat_join_request_service = SimpleNamespace(
        request=lambda chat_id, requester_user_id, message=None: seen.append((chat_id, requester_user_id, message)) or expected
    )

    result = chats_router.request_chat_join(
        "chat-1",
        chats_router.ChatJoinRequestBody(message="please add me"),
        user_id="human-user-2",
        chat_join_request_service=chat_join_request_service,
    )

    assert seen == [("chat-1", "human-user-2", "please add me")]
    assert result == expected


def test_get_chat_join_target_uses_current_token_user() -> None:
    seen: list[tuple[str, str]] = []
    expected = {
        "id": "chat-1",
        "type": "group",
        "title": "Group",
        "status": "active",
        "created_by_user_id": "owner-1",
        "is_member": False,
        "current_request": None,
    }
    chat_join_request_service = SimpleNamespace(join_target=lambda chat_id, user_id: seen.append((chat_id, user_id)) or expected)

    result = chats_router.get_chat_join_target(
        "chat-1",
        user_id="human-user-2",
        chat_join_request_service=chat_join_request_service,
    )

    assert seen == [("chat-1", "human-user-2")]
    assert result == expected


def test_approve_chat_join_uses_current_token_user() -> None:
    seen: list[tuple[str, str, str]] = []
    expected = {
        "id": "join-request-1",
        "chat_id": "chat-1",
        "requester_user_id": "human-user-2",
        "state": "approved",
        "message": "please add me",
        "created_at": 123.0,
        "updated_at": 124.0,
    }
    chat_join_request_service = SimpleNamespace(
        approve=lambda chat_id, request_id, approver_user_id: seen.append((chat_id, request_id, approver_user_id)) or expected
    )

    result = chats_router.approve_chat_join(
        "chat-1",
        "join-request-1",
        chats_router.ChatJoinRequestActionBody(),
        user_id="human-user-1",
        chat_join_request_service=chat_join_request_service,
    )

    assert seen == [("chat-1", "join-request-1", "human-user-1")]
    assert result == expected


def test_get_accessible_chat_or_404_returns_chat():
    chat = _chat("chat-1")
    chat_repo = SimpleNamespace(get_by_id=lambda chat_id: chat if chat_id == "chat-1" else None)
    messaging_service = SimpleNamespace(is_chat_member=lambda chat_id, user_id: (chat_id, user_id) == ("chat-1", "user-1"))

    result = chats_router._get_accessible_chat_or_404(chat_repo, messaging_service, "chat-1", "user-1")

    assert result is chat


def test_get_accessible_chat_or_404_raises_404_for_missing_chat():
    chat_repo = SimpleNamespace(get_by_id=lambda _chat_id: None)
    messaging_service = SimpleNamespace(is_chat_member=lambda _chat_id, _user_id: True)

    with pytest.raises(HTTPException) as exc_info:
        chats_router._get_accessible_chat_or_404(chat_repo, messaging_service, "missing", "user-1")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Chat not found"


def test_get_accessible_chat_or_404_raises_403_for_non_member():
    chat_repo = SimpleNamespace(get_by_id=lambda _chat_id: _chat("chat-1"))
    messaging_service = SimpleNamespace(is_chat_member=lambda _chat_id, _user_id: False)

    with pytest.raises(HTTPException) as exc_info:
        chats_router._get_accessible_chat_or_404(chat_repo, messaging_service, "chat-1", "user-2")

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Not a participant of this chat"


def test_resolve_display_user_delegates_to_messaging_service(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, str]] = []
    expected = SimpleNamespace(id="agent-user-1", display_name="Toad")
    messaging_service = SimpleNamespace(
        resolve_display_user=lambda social_user_id: seen.append(("resolve_display_user", social_user_id)) or expected
    )

    result = chats_router._resolve_display_user(messaging_service, "thread-user-1")

    assert result is expected
    assert seen == [("resolve_display_user", "thread-user-1")]


def test_get_chat_uses_access_helper(monkeypatch: pytest.MonkeyPatch):
    seen: list[tuple[str, object]] = []
    chat = _chat("chat-1")

    def fake_helper(chat_repo, messaging_service, chat_id: str, user_id: str):
        seen.append(("helper", (chat_repo, messaging_service, chat_id, user_id)))
        return chat

    monkeypatch.setattr(chats_router, "_get_accessible_chat_or_404", fake_helper)

    app = SimpleNamespace(
        state=SimpleNamespace(
            chat_runtime_state=SimpleNamespace(
                chat_repo=SimpleNamespace(
                    get_by_id=lambda _chat_id: (_ for _ in ()).throw(
                        AssertionError("route should use helper, not chat_repo lookup directly")
                    )
                ),
                messaging_service=SimpleNamespace(
                    get_chat_detail=lambda chat_obj: {
                        "id": chat_obj.id,
                        "type": chat_obj.type,
                        "title": chat_obj.title,
                        "status": chat_obj.status,
                        "created_at": chat_obj.created_at,
                        "members": [],
                    },
                    list_chat_members=lambda _chat_id: (_ for _ in ()).throw(
                        AssertionError("route should consume service-owned chat detail, not rebuild members locally")
                    ),
                ),
            ),
            user_repo=SimpleNamespace(get_by_id=lambda _user_id: None),
        )
    )

    result = chats_router.get_chat(
        "chat-1",
        user_id="user-1",
        chat_repo=app.state.chat_runtime_state.chat_repo,
        messaging_service=app.state.chat_runtime_state.messaging_service,
    )

    assert result == {
        "id": "chat-1",
        "type": "group",
        "title": "Chat title",
        "status": "active",
        "created_at": "2026-04-07T00:00:00Z",
        "members": [],
    }
    assert seen == [
        ("helper", (app.state.chat_runtime_state.chat_repo, app.state.chat_runtime_state.messaging_service, "chat-1", "user-1"))
    ]


def test_delete_chat_uses_access_helper(monkeypatch: pytest.MonkeyPatch):
    seen: list[tuple[str, object]] = []
    chat = _chat("chat-1")

    def fake_helper(chat_repo, messaging_service, chat_id: str, user_id: str):
        seen.append(("helper", (chat_repo, messaging_service, chat_id, user_id)))
        return chat

    monkeypatch.setattr(chats_router, "_get_accessible_chat_or_404", fake_helper)

    app = SimpleNamespace(
        state=SimpleNamespace(
            chat_runtime_state=SimpleNamespace(
                chat_repo=SimpleNamespace(
                    get_by_id=lambda _chat_id: (_ for _ in ()).throw(
                        AssertionError("route should use helper, not chat_repo lookup directly")
                    ),
                    delete=lambda chat_id: seen.append(("delete", chat_id)),
                ),
                messaging_service=SimpleNamespace(name="messaging"),
            ),
        )
    )

    result = chats_router.delete_chat(
        "chat-1",
        user_id="user-1",
        chat_repo=app.state.chat_runtime_state.chat_repo,
        messaging_service=app.state.chat_runtime_state.messaging_service,
    )

    assert result == {"status": "deleted"}
    assert seen == [
        ("helper", (app.state.chat_runtime_state.chat_repo, app.state.chat_runtime_state.messaging_service, "chat-1", "user-1")),
        ("delete", "chat-1"),
    ]


def test_get_chat_resolves_thread_user_participant_via_thread_repo(monkeypatch: pytest.MonkeyPatch):
    chat = _chat("chat-1")

    monkeypatch.setattr(
        chats_router,
        "_get_accessible_chat_or_404",
        lambda _chat_repo, _messaging_service, _chat_id, _user_id: chat,
    )

    app = SimpleNamespace(
        state=SimpleNamespace(
            chat_runtime_state=SimpleNamespace(
                messaging_service=SimpleNamespace(
                    get_chat_detail=lambda _chat: {
                        "id": "chat-1",
                        "title": "Chat title",
                        "status": "active",
                        "created_at": "2026-04-07T00:00:00Z",
                        "members": [
                            {
                                "id": "thread-user-1",
                                "name": "Toad",
                                "type": "agent",
                                "avatar_url": avatar_url("agent-user-1", False),
                            }
                        ],
                    }
                ),
                chat_repo=SimpleNamespace(name="chat-repo"),
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

    result = chats_router.get_chat(
        "chat-1",
        user_id="human-user-1",
        chat_repo=app.state.chat_runtime_state.chat_repo,
        messaging_service=app.state.chat_runtime_state.messaging_service,
    )

    assert result["members"] == [
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
            chat_runtime_state=SimpleNamespace(
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

    result = chats_router.list_messages(
        "chat-1",
        user_id="human-user-1",
        messaging_service=app.state.chat_runtime_state.messaging_service,
    )

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
            chat_runtime_state=SimpleNamespace(
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
            ),
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


def test_send_message_defaults_sender_to_authenticated_user() -> None:
    seen: list[tuple[str, str, str]] = []
    messaging_service = SimpleNamespace(
        resolve_display_user=lambda uid: (
            SimpleNamespace(
                id="external-user-1",
                display_name="Codex Local",
                type="external",
                avatar=None,
                owner_user_id=None,
            )
            if uid == "external-user-1"
            else None
        ),
        is_chat_member=lambda _chat_id, _user_id: True,
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
            "sender_name": "Codex Local",
            "content": msg["content"],
            "message_type": msg["message_type"],
            "mentioned_ids": [],
            "signal": None,
            "retracted_at": None,
            "created_at": msg["created_at"],
        },
    )

    result = chats_router.send_message(
        "chat-1",
        chats_router.SendMessageBody(content="hello"),
        user_id="external-user-1",
        messaging_service=messaging_service,
    )

    assert seen == [("chat-1", "external-user-1", "hello")]
    assert result["sender_id"] == "external-user-1"


def test_public_send_body_rejects_sender_and_internal_message_controls() -> None:
    with pytest.raises(ValidationError):
        chats_router.SendMessageBody.model_validate(
            {
                "content": "hello",
                "sender_id": "other-user-1",
                "message_type": "system",
                "signal": "yield",
            }
        )


def test_send_message_ignores_external_sender_authority_by_contract() -> None:
    seen: list[dict[str, object]] = []
    messaging_service = SimpleNamespace(
        resolve_display_user=lambda uid: SimpleNamespace(id=uid, owner_user_id=None),
        is_chat_member=lambda _chat_id, _user_id: True,
        send=lambda chat_id, sender_id, content, **kwargs: (
            seen.append({"chat_id": chat_id, "sender_id": sender_id, "content": content, **kwargs})
            or {
                "id": "msg-1",
                "chat_id": chat_id,
                "sender_id": sender_id,
                "content": content,
                "message_type": "human",
                "created_at": "2026-04-07T00:00:00Z",
            }
        ),
        project_message_response=lambda msg: msg,
    )

    chats_router.send_message(
        "chat-1",
        chats_router.SendMessageBody(content="hello", mentioned_ids=["user-2"], enforce_caught_up=True),
        user_id="external-user-1",
        messaging_service=messaging_service,
    )

    assert seen == [
        {
            "chat_id": "chat-1",
            "sender_id": "external-user-1",
            "content": "hello",
            "mentions": ["user-2"],
            "signal": None,
            "message_type": "human",
            "reply_to": None,
            "enforce_caught_up": True,
        }
    ]


def test_send_message_rejects_sender_that_is_not_chat_member() -> None:
    messaging_service = SimpleNamespace(
        resolve_display_user=lambda uid: SimpleNamespace(id=uid, owner_user_id=None),
        is_chat_member=lambda _chat_id, _user_id: False,
        send=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("send should not be called")),
    )

    with pytest.raises(HTTPException) as exc_info:
        chats_router.send_message(
            "chat-1",
            chats_router.SendMessageBody(content="hello"),
            user_id="external-user-1",
            messaging_service=messaging_service,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Not a participant of this chat"


def test_send_message_can_enforce_authenticated_user_caught_up_state() -> None:
    seen: list[dict[str, object]] = []
    messaging_service = SimpleNamespace(
        resolve_display_user=lambda uid: SimpleNamespace(id=uid, owner_user_id=None),
        is_chat_member=lambda _chat_id, _user_id: True,
        send=lambda chat_id, sender_id, content, **kwargs: (
            seen.append({"chat_id": chat_id, "sender_id": sender_id, "content": content, **kwargs})
            or {
                "id": "msg-1",
                "chat_id": chat_id,
                "sender_id": sender_id,
                "content": content,
                "message_type": "human",
                "created_at": "2026-04-07T00:00:00Z",
            }
        ),
        project_message_response=lambda msg: msg,
    )

    chats_router.send_message(
        "chat-1",
        chats_router.SendMessageBody(content="hello", enforce_caught_up=True, reply_to="msg-0"),
        user_id="external-user-1",
        messaging_service=messaging_service,
    )

    assert seen == [
        {
            "chat_id": "chat-1",
            "sender_id": "external-user-1",
            "content": "hello",
            "mentions": None,
            "signal": None,
            "message_type": "human",
            "reply_to": "msg-0",
            "enforce_caught_up": True,
        }
    ]


def test_send_message_maps_caught_up_conflict_to_409() -> None:
    from messaging.errors import ChatNotCaughtUpError

    messaging_service = SimpleNamespace(
        resolve_display_user=lambda uid: SimpleNamespace(id=uid, owner_user_id=None),
        is_chat_member=lambda _chat_id, _user_id: True,
        send=lambda *_args, **_kwargs: (_ for _ in ()).throw(ChatNotCaughtUpError("read unread messages first")),
    )

    with pytest.raises(HTTPException) as exc_info:
        chats_router.send_message(
            "chat-1",
            chats_router.SendMessageBody(content="hello", enforce_caught_up=True),
            user_id="external-user-1",
            messaging_service=messaging_service,
        )

    assert exc_info.value.status_code == 409
    assert "read unread" in str(exc_info.value.detail)


def test_list_unread_messages_uses_authenticated_user_membership() -> None:
    seen: list[tuple[str, str]] = []
    messaging_service = SimpleNamespace(
        is_chat_member=lambda chat_id, user_id: seen.append((chat_id, user_id)) or True,
        list_unread=lambda chat_id, user_id: [{"id": "msg-1", "chat_id": chat_id, "sender_id": "human-1"}],
        project_message_response=lambda msg: {"id": msg["id"], "chat_id": msg["chat_id"], "sender_id": msg["sender_id"]},
    )

    result = chats_router.list_unread_messages(
        "chat-1",
        user_id="external-user-1",
        messaging_service=messaging_service,
    )

    assert seen == [("chat-1", "external-user-1")]
    assert result == [{"id": "msg-1", "chat_id": "chat-1", "sender_id": "human-1"}]


def test_mark_read_rejects_non_member_user() -> None:
    messaging_service = SimpleNamespace(
        is_chat_member=lambda _chat_id, _user_id: False,
        mark_read=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("mark_read should not be called")),
    )

    with pytest.raises(HTTPException) as exc_info:
        chats_router.mark_read(
            "chat-1",
            user_id="external-user-1",
            messaging_service=messaging_service,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Not a participant of this chat"


def test_create_chat_accepts_agent_user_ids_for_group_participants() -> None:
    state, called = _create_chat_route_state(
        users={
            "agent-user-1": SimpleNamespace(id="agent-user-1", type="agent", owner_user_id="owner-user-1"),
            "agent-user-2": SimpleNamespace(id="agent-user-2", type="agent", owner_user_id="owner-user-1"),
        },
        thread_user_ids={"owned-agent-1"},
    )
    app = SimpleNamespace(state=state)

    result = _create_chat(
        app,
        chats_router.CreateChatBody(
            user_ids=["agent-user-1", "agent-user-2"],
            title="agent-group",
        ),
    )

    assert called == [(["human-user-1", "agent-user-1", "agent-user-2"], "agent-group")]
    assert result["id"] == "chat-1"


def test_create_chat_accepts_agent_user_id_for_direct_participant() -> None:
    state, called = _create_chat_route_state(
        users={"agent-user-1": SimpleNamespace(id="agent-user-1", type="agent", owner_user_id="owner-user-1")},
        thread_user_ids={"owned-agent-1"},
        group_route=False,
    )
    app = SimpleNamespace(state=state)

    result = _create_chat(
        app,
        chats_router.CreateChatBody(
            user_ids=["agent-user-1"],
            title=None,
        ),
    )

    assert called == [(["human-user-1", "agent-user-1"], None)]
    assert result["id"] == "chat-1"


def test_create_chat_accepts_human_and_thread_social_user_ids_for_group_participants() -> None:
    state, called = _create_chat_route_state(thread_user_ids={"thread-user-1", "thread-user-2"})
    app = SimpleNamespace(state=state)

    result = _create_chat(
        app,
        chats_router.CreateChatBody(
            user_ids=["thread-user-1", "thread-user-2"],
            title="good-group",
        ),
    )

    assert called == [(["human-user-1", "thread-user-1", "thread-user-2"], "good-group")]
    assert result == {
        "id": "chat-1",
        "title": "good-group",
        "status": "active",
        "created_at": 0,
    }


def test_create_chat_rejects_explicit_authenticated_user_id() -> None:
    state, called = _create_chat_route_state()
    app = SimpleNamespace(state=state)

    with pytest.raises(HTTPException) as exc_info:
        _create_chat(
            app,
            chats_router.CreateChatBody(
                user_ids=["human-user-1", "human-user-2"],
                title="self-member-group",
            ),
        )

    assert exc_info.value.status_code == 400
    assert "authenticated user" in str(exc_info.value.detail).lower()
    assert called == []


def test_create_chat_rejects_empty_other_participants() -> None:
    with pytest.raises(ValidationError) as exc_info:
        chats_router.CreateChatBody(user_ids=[], title="empty-group")

    assert "at least 1 item" in str(exc_info.value)


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

    def _raise_group_policy_error(_user_ids, _title):
        raise ValueError("Active relationship required for group chat participant: human-user-2")

    app.state.chat_runtime_state.messaging_service = SimpleNamespace(create_group_chat=_raise_group_policy_error)

    with pytest.raises(HTTPException) as exc_info:
        _create_chat(
            app,
            chats_router.CreateChatBody(
                user_ids=["owned-agent-1", "human-user-2"],
                title="bad-group",
            ),
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

    result = _create_chat(
        app,
        chats_router.CreateChatBody(
            user_ids=["owned-agent-1", "human-user-2"],
            title="contact-group",
        ),
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

    result = _create_chat(
        app,
        chats_router.CreateChatBody(
            user_ids=["owned-agent-1", "external-agent-1"],
            title="owner-contact-agent-group",
        ),
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

    result = _create_chat(
        app,
        chats_router.CreateChatBody(
            user_ids=["owned-agent-1", "human-user-2"],
            title="good-group",
        ),
    )

    assert called == [(["human-user-1", "owned-agent-1", "human-user-2"], "good-group")]
    assert result["id"] == "chat-1"


def test_create_chat_rejects_unknown_participant_ids_instead_of_falling_to_storage_fk() -> None:
    state, called = _create_chat_route_state()
    app = SimpleNamespace(state=state)

    with pytest.raises(HTTPException) as exc_info:
        _create_chat(
            app,
            chats_router.CreateChatBody(
                user_ids=["thread-id-not-a-user", "thread-user-2"],
                title="bad-group",
            ),
        )

    assert exc_info.value.status_code == 400
    assert "participant" in str(exc_info.value.detail).lower()
    assert called == []
