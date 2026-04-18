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
    delivered: list[tuple[str, str, str, str, str, str | None]] = []

    def deliver(request: ChatDeliveryRequest) -> None:
        delivered.append(
            (
                request.recipient_id,
                request.recipient_user.id,
                request.content,
                request.sender_name,
                request.chat_id,
                request.signal,
            )
        )

    dispatcher = ChatDeliveryDispatcher(
        chat_member_repo=_member_repo(["human-user-1", "agent-user-1"]),
        user_repo=_user_repo(),
        delivery_fn=deliver,
    )

    dispatcher.dispatch("chat-1", "human-user-1", "hello", [], signal="urgent")

    assert delivered == [("agent-user-1", "agent-user-1", "hello", "Human", "chat-1", "urgent")]


def test_dispatcher_same_owner_group_delivers_without_relationship() -> None:
    delivered: list[str] = []
    dispatcher = ChatDeliveryDispatcher(
        chat_member_repo=_member_repo(["human-user-1", "agent-user-1", "agent-user-2"]),
        user_repo=_user_repo(),
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
        delivery_fn=deliver,
    )

    with pytest.raises(RuntimeError, match="agent offline"):
        dispatcher.dispatch("chat-1", "human-user-1", "hello", [])

    assert delivered == []
