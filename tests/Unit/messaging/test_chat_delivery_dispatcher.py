from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from messaging.delivery.actions import DeliveryAction
from messaging.delivery.dispatcher import ChatDeliveryDispatcher, ChatDeliveryRequest


def _user_repo() -> SimpleNamespace:
    def get_by_id(uid: str) -> Any | None:
        users = {
            "human-user-1": SimpleNamespace(
                id="human-user-1",
                display_name="Human",
                type="human",
                avatar=None,
                owner_user_id=None,
            ),
            "outside-human-user": SimpleNamespace(
                id="outside-human-user",
                display_name="Outside",
                type="human",
                avatar=None,
                owner_user_id=None,
            ),
            "agent-user-1": SimpleNamespace(
                id="agent-user-1",
                display_name="Morel",
                type="agent",
                avatar=None,
                owner_user_id="human-user-1",
            ),
            "agent-user-2": SimpleNamespace(
                id="agent-user-2",
                display_name="Toad",
                type="agent",
                avatar=None,
                owner_user_id="human-user-1",
            ),
        }
        return users.get(uid)

    return SimpleNamespace(get_by_id=get_by_id)


def _member_repo(user_ids: list[str]) -> SimpleNamespace:
    return SimpleNamespace(list_members=lambda _chat_id: [{"user_id": uid} for uid in user_ids])


def test_dispatcher_delivers_to_agent_user_ids() -> None:
    delivered: list[tuple[str, str, str, str, str, str, str | None]] = []

    def deliver(request: ChatDeliveryRequest) -> None:
        delivered.append(
            (
                request.recipient_id,
                request.recipient_user.id,
                request.content,
                request.sender_name,
                request.sender_type,
                request.chat_id,
                request.signal,
            )
        )

    dispatcher = ChatDeliveryDispatcher(
        chat_member_repo=_member_repo(["human-user-1", "agent-user-1"]),
        user_repo=_user_repo(),
        avatar_url_builder=lambda _user_id, _has_avatar: None,
        unread_counter=lambda _chat_id, _user_id: 7,
        delivery_fn=deliver,
    )

    dispatcher.dispatch("chat-1", "human-user-1", "hello", [], signal="urgent")

    assert delivered == [("agent-user-1", "agent-user-1", "hello", "Human", "human", "chat-1", "urgent")]


def test_dispatcher_same_owner_group_delivers_without_relationship() -> None:
    delivered: list[str] = []
    dispatcher = ChatDeliveryDispatcher(
        chat_member_repo=_member_repo(["human-user-1", "agent-user-1", "agent-user-2"]),
        user_repo=_user_repo(),
        avatar_url_builder=lambda _user_id, _has_avatar: None,
        unread_counter=lambda _chat_id, _user_id: 0,
        delivery_resolver=SimpleNamespace(
            resolve=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("same-owner path must not call resolver"))
        ),
        delivery_fn=lambda request: delivered.append(request.recipient_id),
    )

    dispatcher.dispatch("chat-1", "human-user-1", "hello", [])

    assert delivered == ["agent-user-1", "agent-user-2"]


def test_dispatcher_agent_turn_delivers_only_to_sibling_agent() -> None:
    delivered: list[str] = []
    dispatcher = ChatDeliveryDispatcher(
        chat_member_repo=_member_repo(["human-user-1", "agent-user-1", "agent-user-2"]),
        user_repo=_user_repo(),
        avatar_url_builder=lambda _user_id, _has_avatar: None,
        unread_counter=lambda _chat_id, _user_id: 0,
        delivery_resolver=SimpleNamespace(
            resolve=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("same-owner sibling path must not call resolver"))
        ),
        delivery_fn=lambda request: delivered.append(request.recipient_id),
    )

    dispatcher.dispatch("chat-1", "agent-user-1", "hello", [])

    assert delivered == ["agent-user-2"]


@pytest.mark.parametrize("action", [DeliveryAction.NOTIFY, DeliveryAction.DROP])
def test_dispatcher_respects_non_deliver_policy(action: DeliveryAction) -> None:
    delivered: list[str] = []
    dispatcher = ChatDeliveryDispatcher(
        chat_member_repo=_member_repo(["outside-human-user", "agent-user-1"]),
        user_repo=_user_repo(),
        avatar_url_builder=lambda _user_id, _has_avatar: None,
        unread_counter=lambda _chat_id, _user_id: 0,
        delivery_resolver=SimpleNamespace(resolve=lambda *_args, **_kwargs: action),
        delivery_fn=lambda request: delivered.append(request.recipient_id),
    )

    dispatcher.dispatch("chat-1", "outside-human-user", "hello", [])

    assert delivered == []


def test_dispatcher_fails_loudly_when_delivery_function_fails() -> None:
    delivered: list[str] = []

    def deliver(request: ChatDeliveryRequest) -> None:
        if request.recipient_id == "agent-user-1":
            raise RuntimeError("agent offline")
        delivered.append(request.recipient_id)

    dispatcher = ChatDeliveryDispatcher(
        chat_member_repo=_member_repo(["human-user-1", "agent-user-1", "agent-user-2"]),
        user_repo=_user_repo(),
        avatar_url_builder=lambda _user_id, _has_avatar: None,
        unread_counter=lambda _chat_id, _user_id: 0,
        delivery_fn=deliver,
    )

    with pytest.raises(RuntimeError, match="agent offline"):
        dispatcher.dispatch("chat-1", "human-user-1", "hello", [])

    assert delivered == []


def test_dispatcher_fails_loudly_when_delivery_function_is_missing() -> None:
    dispatcher = ChatDeliveryDispatcher(
        chat_member_repo=_member_repo(["human-user-1", "agent-user-1"]),
        user_repo=_user_repo(),
        avatar_url_builder=lambda _user_id, _has_avatar: None,
        unread_counter=lambda _chat_id, _user_id: 0,
    )

    with pytest.raises(RuntimeError, match="Chat delivery function is not configured"):
        dispatcher.dispatch("chat-1", "human-user-1", "hello", [])


def test_dispatcher_fails_loudly_when_sender_identity_is_missing() -> None:
    delivered: list[str] = []
    dispatcher = ChatDeliveryDispatcher(
        chat_member_repo=_member_repo(["missing-user", "agent-user-1"]),
        user_repo=_user_repo(),
        avatar_url_builder=lambda _user_id, _has_avatar: None,
        unread_counter=lambda _chat_id, _user_id: 0,
        delivery_fn=lambda request: delivered.append(request.recipient_id),
    )

    with pytest.raises(RuntimeError, match="Chat delivery sender identity not found: missing-user"):
        dispatcher.dispatch("chat-1", "missing-user", "hello", [])

    assert delivered == []


def test_dispatcher_fails_loudly_when_member_user_id_is_missing() -> None:
    delivered: list[str] = []
    dispatcher = ChatDeliveryDispatcher(
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: [{"user_id": "human-user-1"}, {}]),
        user_repo=_user_repo(),
        avatar_url_builder=lambda _user_id, _has_avatar: None,
        unread_counter=lambda _chat_id, _user_id: 0,
        delivery_fn=lambda request: delivered.append(request.recipient_id),
    )

    with pytest.raises(RuntimeError, match="Chat delivery member row is missing user_id in chat chat-1"):
        dispatcher.dispatch("chat-1", "human-user-1", "hello", [])

    assert delivered == []


def test_dispatcher_fails_loudly_when_recipient_identity_is_missing() -> None:
    delivered: list[str] = []
    dispatcher = ChatDeliveryDispatcher(
        chat_member_repo=_member_repo(["human-user-1", "missing-recipient"]),
        user_repo=_user_repo(),
        avatar_url_builder=lambda _user_id, _has_avatar: None,
        unread_counter=lambda _chat_id, _user_id: 0,
        delivery_fn=lambda request: delivered.append(request.recipient_id),
    )

    with pytest.raises(RuntimeError, match="Chat delivery recipient identity not found: missing-recipient"):
        dispatcher.dispatch("chat-1", "human-user-1", "hello", [])

    assert delivered == []


def test_dispatcher_uses_injected_avatar_url_builder_for_sender() -> None:
    built: list[tuple[str | None, bool]] = []
    delivered: list[str | None] = []

    def _user_with_avatar_repo() -> SimpleNamespace:
        return SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Human", type="human", avatar="avatars/human.png", owner_user_id=None)
                if uid == "human-user-1"
                else SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None, owner_user_id="human-user-1")
                if uid == "agent-user-1"
                else None
            )
        )

    dispatcher = ChatDeliveryDispatcher(
        chat_member_repo=_member_repo(["human-user-1", "agent-user-1"]),
        user_repo=_user_with_avatar_repo(),
        unread_counter=lambda _chat_id, _user_id: 0,
        avatar_url_builder=lambda user_id, has_avatar: built.append((user_id, has_avatar)) or f"custom:{user_id}:{has_avatar}",
        delivery_fn=lambda request: delivered.append(request.sender_avatar_url),
    )

    dispatcher.dispatch("chat-1", "human-user-1", "hello", [])

    assert built == [("human-user-1", True)]
    assert delivered == ["custom:human-user-1:True"]
