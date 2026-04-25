from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from typing import Any, cast

import pytest

from backend.identity.avatar.urls import avatar_url
from backend.threads.chat_adapters import chat_inlet as chat_delivery_hook
from backend.threads.chat_adapters.bootstrap import build_agent_runtime_state
from core.runtime.middleware.monitor import AgentState
from core.runtime.registry import ToolRegistry
from core.runtime.tool_result import ToolResultEnvelope
from messaging.delivery.actions import DeliveryAction
from messaging.delivery.contracts import ChatDeliveryRequest
from messaging.delivery.dispatcher import ChatDeliveryDispatcher
from messaging.delivery.resolver import HireVisitDeliveryResolver
from messaging.display_user import resolve_messaging_display_user
from messaging.relationships.service import RelationshipService
from messaging.service import MessagingService
from messaging.tools.chat_tool_service import ChatToolService
from storage.contracts import ContactEdgeRow

_MessagingService = MessagingService
_ChatDeliveryDispatcher = ChatDeliveryDispatcher


def MessagingService(*args, **kwargs):  # noqa: N802
    kwargs.setdefault("avatar_url_builder", avatar_url)
    return _MessagingService(*args, **kwargs)


def ChatDeliveryDispatcher(*args, **kwargs):  # noqa: N802
    kwargs.setdefault("avatar_url_builder", avatar_url)
    return _ChatDeliveryDispatcher(*args, **kwargs)


class _FakeRelationshipRepo:
    def __init__(self) -> None:
        self._existing = {
            ("agent-user-1", "human-user-1"): {
                "id": "hire_visit:agent-user-1:human-user-1",
                "user_low": "agent-user-1",
                "user_high": "human-user-1",
                "kind": "hire_visit",
                "state": "hire",
                "initiator_user_id": "human-user-1",
                "created_at": "2026-04-07T00:00:00Z",
                "updated_at": "2026-04-07T00:00:00Z",
            }
        }

    def get(self, requester_id: str, target_id: str):
        key = cast(tuple[str, str], tuple(sorted((requester_id, target_id))))
        return self._existing.get(key)

    def upsert(self, requester_id: str, target_id: str, *, state: str, initiator_user_id: str | None):
        key = cast(tuple[str, str], tuple(sorted((requester_id, target_id))))
        row = dict(self._existing[key])
        row.update({"state": state, "initiator_user_id": initiator_user_id})
        row["updated_at"] = "2026-04-07T00:01:00Z"
        self._existing[key] = row
        return row


def _messaging_display_service(**overrides: Any) -> SimpleNamespace:
    def _resolve_display_user(uid: str) -> Any | None:
        if uid == "agent-user-1":
            return SimpleNamespace(id="agent-user-1", display_name="Toad", owner_user_id="owner-user-1")
        return None

    payload = {"resolve_display_user": _resolve_display_user}
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_messaging_display_user_resolver_prefers_direct_user_row() -> None:
    resolved = resolve_messaging_display_user(
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None) if uid == "human-user-1" else None
            )
        ),
        social_user_id="human-user-1",
    )

    assert resolved is not None
    assert resolved.display_name == "Human"


def test_deliver_to_agents_does_not_require_main_thread_id():
    delivered: list[tuple[str, str]] = []
    dispatcher = ChatDeliveryDispatcher(
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: [{"user_id": "agent-user-1"}]),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None)
                if uid == "agent-user-1"
                else SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None)
            )
        ),
        unread_counter=lambda _chat_id, _user_id: 0,
        delivery_fn=lambda request: delivered.append((request.recipient_id, request.recipient_user.id)),
    )

    dispatcher.dispatch("chat-1", "human-user-1", "hello", [])

    assert delivered == [("agent-user-1", "agent-user-1")]


def test_relationship_revoke_deletes_hire_without_snapshot_side_channel() -> None:
    repo = _FakeRelationshipRepo()
    service = RelationshipService(repo)

    row = service.revoke("human-user-1", "agent-user-1")

    assert row.state == "none"


def test_relationship_request_uses_single_pending_state_and_initiator() -> None:
    class _RequestRepo:
        def get(self, _requester_id: str, _target_id: str):
            return None

        def upsert(self, _requester_id: str, _target_id: str, **fields: Any):
            return {
                "id": "hire_visit:agent-user-1:human-user-1",
                "user_low": "agent-user-1",
                "user_high": "human-user-1",
                "kind": "hire_visit",
                "created_at": "2026-04-07T00:00:00Z",
                "updated_at": "2026-04-07T00:00:01Z",
                **fields,
            }

    service = RelationshipService(_RequestRepo())

    row = service.request("human-user-1", "agent-user-1")

    assert row.state == "pending"
    assert row.initiator_user_id == "human-user-1"


def test_relationship_list_for_user_fails_on_invalid_row() -> None:
    service = RelationshipService(
        SimpleNamespace(
            list_for_user=lambda _user_id: [
                {
                    "id": "hire_visit:agent-user-1:human-user-1",
                    "user_low": "agent-user-1",
                    "user_high": "human-user-1",
                    "kind": "hire_visit",
                    "state": "visit",
                    "created_at": "2026-04-07T00:00:00Z",
                }
            ]
        )
    )

    with pytest.raises(RuntimeError, match="Invalid relationship row hire_visit:agent-user-1:human-user-1"):
        service.list_for_user("human-user-1")


def test_relationship_get_state_fails_on_invalid_existing_row() -> None:
    service = RelationshipService(
        SimpleNamespace(
            get=lambda _user_a, _user_b: {
                "id": "hire_visit:agent-user-1:human-user-1",
                "user_low": "agent-user-1",
                "user_high": "human-user-1",
                "kind": "hire_visit",
                "created_at": "2026-04-07T00:00:00Z",
                "updated_at": "2026-04-07T00:00:01Z",
            }
        )
    )

    with pytest.raises(RuntimeError, match="Invalid relationship row hire_visit:agent-user-1:human-user-1"):
        service.get_state("human-user-1", "agent-user-1")


def test_chat_tool_registry_exposes_final_contract_only() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="owner-user-1",
        messaging_service=_messaging_display_service(),
    )

    for tool_name in ("list_chats", "read_messages", "send_message", "search_messages"):
        assert registry.get(tool_name) is not None


def test_send_message_schema_uses_participant_id_for_direct_chat() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="agent-user-1",
    )

    send_message = registry.get("send_message")
    assert send_message is not None

    send_message_schema = send_message.get_schema()

    assert "participant_id" in send_message_schema["parameters"]["properties"]
    assert "user_id" not in send_message_schema["parameters"]["properties"]
    assert "leg" + "acy" not in send_message_schema["description"].lower()
    assert "directory" not in send_message_schema["description"].lower()
    assert send_message_schema["parameters"]["x-leon-required-any-of"] == [["participant_id"], ["chat_id"]]


def test_read_messages_schema_requires_non_empty_chat_or_user_identifier() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="agent-user-1",
    )

    read_messages = registry.get("read_messages")
    assert read_messages is not None

    params = read_messages.get_schema()["parameters"]

    assert params["x-leon-required-any-of"] == [["participant_id"], ["chat_id"]]
    assert params["properties"]["participant_id"]["minLength"] == 1
    assert "user_id" not in params["properties"]
    assert params["properties"]["chat_id"]["minLength"] == 1


def test_chat_tool_service_accepts_chat_identity_id_contract() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="agent-user-1",
        messaging_service=_messaging_display_service(),
    )

    assert registry.get("list_chats") is not None


def test_chat_tool_list_chats_uses_messaging_service_title() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_chats_for_user=lambda _user_id: [
                {
                    "id": "chat-1",
                    "title": "Solo Ops",
                    "members": [{"id": "human-user-1", "name": "Human"}],
                    "unread_count": 0,
                    "last_message": None,
                }
            ],
        ),
    )

    list_chats = registry.get("list_chats")
    assert list_chats is not None

    result = list_chats.handler()

    assert result == "- Solo Ops"


def test_chat_tool_list_chats_requires_members_contract() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_chats_for_user=lambda _user_id: [
                {
                    "id": "chat-1",
                    "title": "Solo Ops",
                    "unread_count": 0,
                    "last_message": None,
                }
            ],
        ),
    )

    list_chats = registry.get("list_chats")
    assert list_chats is not None

    with pytest.raises(RuntimeError, match="Chat summary chat-1 is missing members"):
        list_chats.handler()


def test_chat_tool_list_chats_requires_summary_rows_to_be_objects_contract() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_chats_for_user=lambda _user_id: ["chat-1"],
        ),
    )

    list_chats = registry.get("list_chats")
    assert list_chats is not None

    with pytest.raises(RuntimeError) as excinfo:
        list_chats.handler()

    assert str(excinfo.value) == "Chat summary row is invalid"


def test_chat_tool_list_chats_requires_summary_collection_contract() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_chats_for_user=lambda _user_id: {"id": "chat-1"},
        ),
    )

    list_chats = registry.get("list_chats")
    assert list_chats is not None

    with pytest.raises(RuntimeError) as excinfo:
        list_chats.handler()

    assert str(excinfo.value) == "Chat summary collection is invalid"


def test_chat_tool_list_chats_requires_member_rows_to_be_objects_contract() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_chats_for_user=lambda _user_id: [
                {
                    "id": "chat-1",
                    "title": "Solo Ops",
                    "members": ["human-user-1"],
                    "unread_count": 0,
                    "last_message": None,
                }
            ],
        ),
    )

    list_chats = registry.get("list_chats")
    assert list_chats is not None

    with pytest.raises(RuntimeError) as excinfo:
        list_chats.handler()

    assert str(excinfo.value) == "Chat summary chat-1 member row is invalid"


def test_chat_tool_list_chats_requires_member_ids_contract() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_chats_for_user=lambda _user_id: [
                {
                    "id": "chat-1",
                    "title": "Solo Ops",
                    "members": [{"name": "Human"}],
                    "unread_count": 0,
                    "last_message": None,
                }
            ],
        ),
    )

    list_chats = registry.get("list_chats")
    assert list_chats is not None

    with pytest.raises(RuntimeError, match="Chat summary chat-1 member row is missing id"):
        list_chats.handler()


def test_chat_tool_list_chats_requires_string_member_ids_contract() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_chats_for_user=lambda _user_id: [
                {
                    "id": "chat-1",
                    "title": "Solo Ops",
                    "members": [{"id": None, "name": "Human"}],
                    "unread_count": 0,
                    "last_message": None,
                }
            ],
        ),
    )

    list_chats = registry.get("list_chats")
    assert list_chats is not None

    with pytest.raises(RuntimeError) as excinfo:
        list_chats.handler()

    assert str(excinfo.value) == "Chat summary chat-1 member row has invalid id"


def test_chat_tool_list_chats_requires_group_chat_id_contract() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_chats_for_user=lambda _user_id: [
                {
                    "title": "Ops Room",
                    "members": [
                        {"id": "human-user-1", "name": "Human"},
                        {"id": "agent-user-1", "name": "Agent"},
                        {"id": "agent-user-2", "name": "Agent 2"},
                    ],
                    "unread_count": 0,
                    "last_message": None,
                }
            ],
        ),
    )

    list_chats = registry.get("list_chats")
    assert list_chats is not None

    with pytest.raises(RuntimeError, match="Group chat summary is missing id"):
        list_chats.handler()


def test_chat_tool_list_chats_requires_string_group_chat_id_contract() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_chats_for_user=lambda _user_id: [
                {
                    "id": 123,
                    "title": "Ops Room",
                    "members": [
                        {"id": "human-user-1", "name": "Human"},
                        {"id": "agent-user-1", "name": "Agent"},
                        {"id": "agent-user-2", "name": "Agent 2"},
                    ],
                    "unread_count": 0,
                    "last_message": None,
                }
            ],
        ),
    )

    list_chats = registry.get("list_chats")
    assert list_chats is not None

    with pytest.raises(RuntimeError) as excinfo:
        list_chats.handler()

    assert str(excinfo.value) == "Group chat summary has invalid id"


def test_chat_tool_list_chats_requires_last_message_content_contract() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_chats_for_user=lambda _user_id: [
                {
                    "id": "chat-1",
                    "title": "Solo Ops",
                    "members": [{"id": "human-user-1", "name": "Human"}],
                    "unread_count": 0,
                    "last_message": {"id": "msg-1"},
                }
            ],
        ),
    )

    list_chats = registry.get("list_chats")
    assert list_chats is not None

    with pytest.raises(RuntimeError, match="Chat summary chat-1 last_message is missing content"):
        list_chats.handler()


def test_chat_tool_list_chats_requires_last_message_row_to_be_object_contract() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_chats_for_user=lambda _user_id: [
                {
                    "id": "chat-1",
                    "title": "Solo Ops",
                    "members": [{"id": "human-user-1", "name": "Human"}],
                    "unread_count": 0,
                    "last_message": "message-1",
                }
            ],
        ),
    )

    list_chats = registry.get("list_chats")
    assert list_chats is not None

    with pytest.raises(RuntimeError) as excinfo:
        list_chats.handler()

    assert str(excinfo.value) == "Chat summary chat-1 last_message row is invalid"


def test_chat_tool_list_chats_requires_string_title_contract() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_chats_for_user=lambda _user_id: [
                {
                    "id": "chat-1",
                    "title": 123,
                    "members": [{"id": "human-user-1", "name": "Human"}],
                    "unread_count": 0,
                    "last_message": None,
                }
            ],
        ),
    )

    list_chats = registry.get("list_chats")
    assert list_chats is not None

    with pytest.raises(RuntimeError) as excinfo:
        list_chats.handler()

    assert str(excinfo.value) == "Chat summary chat-1 has invalid title"


def test_chat_tool_list_chats_requires_empty_last_message_content_contract() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_chats_for_user=lambda _user_id: [
                {
                    "id": "chat-1",
                    "title": "Solo Ops",
                    "members": [{"id": "human-user-1", "name": "Human"}],
                    "unread_count": 0,
                    "last_message": {},
                }
            ],
        ),
    )

    list_chats = registry.get("list_chats")
    assert list_chats is not None

    with pytest.raises(RuntimeError, match="Chat summary chat-1 last_message is missing content"):
        list_chats.handler()


def test_chat_tool_list_chats_requires_string_last_message_content_contract() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_chats_for_user=lambda _user_id: [
                {
                    "id": "chat-1",
                    "title": "Solo Ops",
                    "members": [{"id": "human-user-1", "name": "Human"}],
                    "unread_count": 0,
                    "last_message": {"content": None},
                }
            ],
        ),
    )

    list_chats = registry.get("list_chats")
    assert list_chats is not None

    with pytest.raises(RuntimeError) as excinfo:
        list_chats.handler()

    assert str(excinfo.value) == "Chat summary chat-1 last_message has invalid content"


def test_chat_tool_list_chats_requires_unread_count_contract() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_chats_for_user=lambda _user_id: [
                {
                    "id": "chat-1",
                    "title": "Solo Ops",
                    "members": [{"id": "human-user-1", "name": "Human"}],
                    "last_message": None,
                }
            ],
        ),
    )

    list_chats = registry.get("list_chats")
    assert list_chats is not None

    with pytest.raises(RuntimeError, match="Chat summary chat-1 is missing unread_count"):
        list_chats.handler()


def test_chat_tool_list_chats_requires_integer_unread_count_contract() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_chats_for_user=lambda _user_id: [
                {
                    "id": "chat-1",
                    "title": "Solo Ops",
                    "members": [{"id": "human-user-1", "name": "Human"}],
                    "unread_count": None,
                    "last_message": None,
                }
            ],
        ),
    )

    list_chats = registry.get("list_chats")
    assert list_chats is not None

    with pytest.raises(RuntimeError) as excinfo:
        list_chats.handler()

    assert str(excinfo.value) == "Chat summary chat-1 has invalid unread_count"


def test_chat_tool_list_chats_unread_filter_requires_unread_count_contract() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_chats_for_user=lambda _user_id: [
                {
                    "id": "chat-1",
                    "title": "Solo Ops",
                    "members": [{"id": "human-user-1", "name": "Human"}],
                    "last_message": None,
                }
            ],
        ),
    )

    list_chats = registry.get("list_chats")
    assert list_chats is not None

    with pytest.raises(RuntimeError, match="Chat summary chat-1 is missing unread_count"):
        list_chats.handler(unread_only=True)


@pytest.mark.parametrize("chat_identity_id", [None, ""])
def test_chat_tool_service_rejects_empty_chat_identity_id(chat_identity_id: str | None) -> None:
    registry = ToolRegistry()

    with pytest.raises(ValueError, match="chat_identity_id"):
        ChatToolService(
            registry=registry,
            chat_identity_id=chat_identity_id,  # type: ignore[arg-type]
            messaging_service=_messaging_display_service(),
        )


def test_chat_tool_service_rejects_dead_repo_constructor_kwargs() -> None:
    registry = ToolRegistry()

    with pytest.raises(TypeError, match="chat_member_repo|messages_repo|owner_id|relationship_repo|user_repo|thread_repo"):
        ChatToolService(
            registry=registry,
            chat_identity_id="agent-user-1",
            owner_id="owner-user-1",
            messaging_service=SimpleNamespace(),
            chat_member_repo=SimpleNamespace(),
            relationship_repo=SimpleNamespace(),
            user_repo=SimpleNamespace(),
        )


def test_messaging_service_resolves_sender_name_from_agent_user_id() -> None:
    published: list[dict[str, object]] = []
    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: []),
        messages_repo=SimpleNamespace(create=lambda row: row),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None)
                if uid == "human-user-1"
                else SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None)
                if uid == "agent-user-1"
                else None
            )
        ),
        event_bus=SimpleNamespace(publish=lambda _chat_id, payload: published.append(payload)),
    )

    service.send("chat-1", "agent-user-1", "hello")

    payload = cast(dict[str, object], published[0])
    data = cast(dict[str, object], payload["data"])
    assert data["sender_name"] == "Toad"


def test_messaging_service_event_bus_message_uses_service_owned_projection() -> None:
    published: list[dict[str, object]] = []
    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: []),
        messages_repo=SimpleNamespace(create=lambda row: row),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None)
                if uid == "human-user-1"
                else SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None)
                if uid == "agent-user-1"
                else None
            )
        ),
        event_bus=SimpleNamespace(publish=lambda _chat_id, payload: published.append(payload)),
    )

    created = service.send("chat-1", "agent-user-1", "hello", mentions=["human-user-1"], signal="open")

    payload = cast(dict[str, object], published[0])
    assert payload == {
        "event": "message",
        "data": service.project_message_response(created),
    }


def test_messaging_service_notification_mentions_dispatch_to_agent_recipients() -> None:
    delivered: list[str] = []

    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: [{"user_id": "managed-owner-1"}]),
        messages_repo=SimpleNamespace(
            create=lambda row: row,
            count_unread=lambda _chat_id, _user_id: 1,
        ),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(
                    id="visitor-1",
                    display_name="Visitor",
                    type="human",
                    avatar=None,
                    owner_user_id=None,
                )
                if uid == "visitor-1"
                else SimpleNamespace(
                    id="managed-owner-1",
                    display_name="Managed Owner",
                    type="agent",
                    avatar=None,
                    owner_user_id="human-owner-1",
                )
                if uid == "managed-owner-1"
                else None
            )
        ),
        delivery_resolver=SimpleNamespace(
            resolve=lambda _recipient_id, _chat_id, _sender_id, *, is_mentioned: (
                DeliveryAction.DELIVER if is_mentioned else DeliveryAction.DROP
            )
        ),
        delivery_fn=lambda request: delivered.append(request.recipient_id),
    )

    service.send(
        "chat-1",
        "visitor-1",
        "visitor-1 requested to join this chat.",
        message_type="notification",
        mentions=["managed-owner-1"],
    )

    assert delivered == ["managed-owner-1"]


def test_messaging_service_send_fails_before_persisting_unknown_sender() -> None:
    created_rows: list[dict[str, Any]] = []
    published: list[dict[str, object]] = []
    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: []),
        messages_repo=SimpleNamespace(create=lambda row: created_rows.append(row) or row),
        user_repo=SimpleNamespace(get_by_id=lambda _uid: None),
        event_bus=SimpleNamespace(publish=lambda _chat_id, payload: published.append(payload)),
    )

    with pytest.raises(RuntimeError, match="Chat message sender identity not found: missing-user"):
        service.send("chat-1", "missing-user", "hello")

    assert created_rows == []
    assert published == []


def test_messaging_service_list_message_responses_projects_sender_name_from_agent_user_id() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(),
        messages_repo=SimpleNamespace(
            list_by_chat=lambda _chat_id, **_kwargs: [
                {
                    "id": "msg-1",
                    "chat_id": "chat-1",
                    "sender_user_id": "agent-user-1",
                    "content": "hello",
                    "message_type": "human",
                    "created_at": "2026-04-07T00:00:00Z",
                }
            ]
        ),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None) if uid == "agent-user-1" else None
        ),
    )

    result = service.list_message_responses("chat-1", viewer_id="human-user-1")

    assert result == [
        {
            "id": "msg-1",
            "chat_id": "chat-1",
            "sender_id": "agent-user-1",
            "sender_name": "Toad",
            "content": "hello",
            "message_type": "human",
            "mentioned_ids": [],
            "signal": None,
            "retracted_at": None,
            "created_at": "2026-04-07T00:00:00Z",
        }
    ]


def test_messaging_service_list_message_responses_fails_on_unknown_sender() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(),
        messages_repo=SimpleNamespace(
            list_by_chat=lambda _chat_id, **_kwargs: [
                {
                    "id": "msg-1",
                    "chat_id": "chat-1",
                    "sender_user_id": "missing-user",
                    "content": "hello",
                    "message_type": "human",
                    "created_at": "2026-04-07T00:00:00Z",
                }
            ]
        ),
        user_repo=SimpleNamespace(get_by_id=lambda _uid: None),
    )

    with pytest.raises(RuntimeError) as excinfo:
        service.list_message_responses("chat-1", viewer_id="human-user-1")

    assert str(excinfo.value) == "Chat message sender identity not found: missing-user"


def test_messaging_service_agent_send_passes_expected_read_seq_to_messages_repo() -> None:
    created_rows: list[tuple[dict[str, Any], int | None]] = []

    class _StatefulChatMemberRepo:
        def list_members(self, _chat_id: str) -> list[dict[str, Any]]:
            return []

        def last_read_seq(self, chat_id: str, user_id: str) -> int:
            assert chat_id == "chat-1"
            assert user_id == "agent-user-1"
            return 7

    class _MessagesRepo:
        def create(self, row: dict[str, Any], expected_read_seq: int | None = None) -> dict[str, Any]:
            created_rows.append((row, expected_read_seq))
            return {**row, "seq": 8}

    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=_StatefulChatMemberRepo(),
        messages_repo=_MessagesRepo(),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None) if uid == "agent-user-1" else None
        ),
    )

    service.send("chat-1", "agent-user-1", "hello", enforce_caught_up=True)

    assert len(created_rows) == 1
    row, expected_read_seq = created_rows[0]
    assert row["sender_user_id"] == "agent-user-1"
    assert expected_read_seq == 7


def test_messaging_service_agent_send_maps_storage_conflict_to_not_caught_up_error() -> None:
    from messaging.errors import ChatNotCaughtUpError
    from storage.errors import StorageConflictError

    class _StatefulChatMemberRepo:
        def list_members(self, _chat_id: str) -> list[dict[str, Any]]:
            return []

        def last_read_seq(self, chat_id: str, user_id: str) -> int:
            assert chat_id == "chat-1"
            assert user_id == "agent-user-1"
            return 7

    class _MessagesRepo:
        def create(self, row: dict[str, Any], expected_read_seq: int | None = None) -> dict[str, Any]:
            raise StorageConflictError("Chat advanced after your last read.")

    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=_StatefulChatMemberRepo(),
        messages_repo=_MessagesRepo(),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None) if uid == "agent-user-1" else None
        ),
    )

    with pytest.raises(ChatNotCaughtUpError) as excinfo:
        service.send("chat-1", "agent-user-1", "hello", enforce_caught_up=True)

    assert str(excinfo.value) == "Chat advanced after your last read."


def test_messaging_service_list_chats_exposes_agent_user_participant_id() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda chat_ids: [
                SimpleNamespace(
                    id=chat_id,
                    title=None,
                    status="active",
                    created_at="2026-04-07T00:00:00Z",
                    updated_at="2026-04-07T00:00:00Z",
                )
                for chat_id in chat_ids
            ],
            get_by_id=lambda _chat_id: (_ for _ in ()).throw(AssertionError("chat list should not fetch chats one by one")),
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [
                {"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 0},
                {"chat_id": "chat-1", "user_id": "agent-user-1", "last_read_seq": 0},
            ],
            list_members=lambda _chat_id: (_ for _ in ()).throw(AssertionError("chat list should not fetch members one by one")),
        ),
        messages_repo=SimpleNamespace(
            list_latest_by_chat_ids=lambda _chat_ids: {},
            count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {"chat-1": 0},
            list_by_chat=lambda _chat_id, limit=1: (_ for _ in ()).throw(
                AssertionError("chat list should not fetch messages one chat at a time")
            ),
            count_unread=lambda _chat_id, _user_id: (_ for _ in ()).throw(
                AssertionError("chat list should not count unread one chat at a time")
            ),
        ),
        user_repo=SimpleNamespace(
            list_by_ids=lambda user_ids: [
                SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None)
                if uid == "human-user-1"
                else SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None)
                for uid in user_ids
            ],
            get_by_id=lambda _uid: (_ for _ in ()).throw(AssertionError("chat list should not fetch users one by one")),
        ),
        thread_repo=SimpleNamespace(get_by_user_id=lambda _uid: (_ for _ in ()).throw(AssertionError("agent users are direct chat ids"))),
    )

    chats = service.list_chats_for_user("human-user-1")

    assert chats[0]["members"] == [
        {
            "id": "human-user-1",
            "name": "Human",
            "type": "human",
            "avatar_url": avatar_url("human-user-1", False),
        },
        {
            "id": "agent-user-1",
            "name": "Toad",
            "type": "agent",
            "avatar_url": avatar_url("agent-user-1", False),
        },
    ]
    assert chats[0]["title"] == "Toad"
    assert chats[0]["avatar_url"] == avatar_url("agent-user-1", False)
    assert chats[0]["updated_at"] == "2026-04-07T00:00:00Z"
    assert chats[0]["unread_count"] == 0


def test_messaging_service_chat_detail_fails_on_unknown_member_identity() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(
            list_members=lambda _chat_id: [
                {"user_id": "human-user-1"},
                {"user_id": "missing-user"},
            ],
        ),
        messages_repo=SimpleNamespace(),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None) if uid == "human-user-1" else None
            ),
        ),
    )

    chat = SimpleNamespace(
        id="chat-1",
        title=None,
        status="active",
        created_by_user_id="human-user-1",
        created_at="2026-04-07T00:00:00Z",
    )

    with pytest.raises(RuntimeError) as excinfo:
        service.get_chat_detail(chat)

    assert str(excinfo.value) == "Chat member missing-user is not a resolvable user row"


def test_messaging_service_rejects_unknown_direct_chat_participant_before_writing() -> None:
    writes: list[tuple[str, str] | str] = []

    service = MessagingService(
        chat_repo=SimpleNamespace(
            create=lambda _row: writes.append("chat"),
            get_by_id=lambda _chat_id: (_ for _ in ()).throw(AssertionError("unknown participant must fail before lookup")),
        ),
        chat_member_repo=SimpleNamespace(
            find_chat_between=lambda _requester_id, _target_id: (_ for _ in ()).throw(
                AssertionError("unknown participant must fail before member lookup")
            ),
            add_member=lambda chat_id, user_id: writes.append((chat_id, user_id)),
        ),
        messages_repo=SimpleNamespace(),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None) if uid == "human-user-1" else None
            ),
        ),
    )

    with pytest.raises(ValueError) as excinfo:
        service.find_or_create_chat(["human-user-1", "missing-user"])

    assert str(excinfo.value) == "Chat participant missing-user is not a resolvable user row"
    assert writes == []


def test_messaging_service_list_chats_ignores_blank_other_names_in_title_default() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda chat_ids: [
                SimpleNamespace(id=chat_id, title=None, status="active", created_at="2026-04-07T00:00:00Z", updated_at=None)
                for chat_id in chat_ids
            ],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [
                {"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 0},
                {"chat_id": "chat-1", "user_id": "agent-user-blank", "last_read_seq": 0},
                {"chat_id": "chat-1", "user_id": "agent-user-1", "last_read_seq": 0},
            ],
        ),
        messages_repo=SimpleNamespace(
            list_latest_by_chat_ids=lambda _chat_ids: {},
            count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {"chat-1": 0},
        ),
        user_repo=SimpleNamespace(
            list_by_ids=lambda user_ids: [
                SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None)
                if uid == "human-user-1"
                else SimpleNamespace(id=uid, display_name="", type="agent", avatar=None)
                if uid == "agent-user-blank"
                else SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None)
                for uid in user_ids
            ]
        ),
    )

    chats = service.list_chats_for_user("human-user-1")

    assert chats[0]["title"] == "Toad"


def test_messaging_service_conversation_summaries_use_bulk_projection_repos() -> None:
    calls: list[str] = []
    user_rows = {
        "human-user-1": SimpleNamespace(id="human-user-1", display_name="Human", type="human", avatar=None),
        "agent-user-1": SimpleNamespace(id="agent-user-1", display_name="Toad", type="agent", avatar=None),
    }

    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda chat_ids: (
                calls.append(f"chats:{','.join(chat_ids)}")
                or [
                    SimpleNamespace(
                        id="chat-1",
                        title=None,
                        status="active",
                        created_at=1.0,
                        updated_at=2.0,
                    ),
                    SimpleNamespace(
                        id="chat-closed",
                        title="Closed",
                        status="closed",
                        created_at=1.0,
                        updated_at=2.0,
                    ),
                ]
            ),
            get_by_id=lambda _chat_id: (_ for _ in ()).throw(AssertionError("conversation summaries must not fetch chats one by one")),
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda user_id: calls.append(f"chat-ids:{user_id}") or ["chat-1", "chat-closed"],
            list_members_for_chats=lambda chat_ids: (
                calls.append(f"members:{','.join(chat_ids)}")
                or [
                    member
                    for member in [
                        {"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 4},
                        {"chat_id": "chat-1", "user_id": "agent-user-1", "last_read_seq": 0},
                        {"chat_id": "chat-closed", "user_id": "human-user-1", "last_read_seq": 0},
                    ]
                    if member["chat_id"] in chat_ids
                ]
            ),
            list_members=lambda _chat_id: (_ for _ in ()).throw(AssertionError("conversation summaries must not fetch members one by one")),
        ),
        messages_repo=SimpleNamespace(
            count_unread_by_chat_ids=lambda user_id, last_read_by_chat: (
                calls.append(f"unread:{user_id}:{last_read_by_chat}") or {"chat-1": 2}
            ),
            list_by_chat=lambda _chat_id, limit=1: (_ for _ in ()).throw(
                AssertionError("conversation summaries must not fetch latest messages")
            ),
            count_unread=lambda _chat_id, _user_id: (_ for _ in ()).throw(
                AssertionError("conversation summaries must not count unread one by one")
            ),
        ),
        user_repo=SimpleNamespace(
            list_by_ids=lambda user_ids: calls.append(f"users:{','.join(user_ids)}") or [user_rows[user_id] for user_id in user_ids],
            get_by_id=lambda _uid: (_ for _ in ()).throw(AssertionError("conversation summaries must not fetch users one by one")),
        ),
        thread_repo=SimpleNamespace(
            get_by_user_id=lambda _uid: (_ for _ in ()).throw(AssertionError("direct user ids should not query threads"))
        ),
    )

    summaries = service.list_conversation_summaries_for_user("human-user-1")

    assert summaries == [
        {
            "id": "chat-1",
            "title": "Toad",
            "avatar_url": avatar_url("agent-user-1", False),
            "updated_at": 2.0,
            "unread_count": 2,
        }
    ]
    assert calls == [
        "chat-ids:human-user-1",
        "chats:chat-1,chat-closed",
        "members:chat-1",
        "users:agent-user-1,human-user-1",
        "unread:human-user-1:{'chat-1': 4}",
    ]


def test_messaging_service_conversation_summaries_fail_on_unknown_member_identity() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda _chat_ids: [SimpleNamespace(id="chat-1", title=None, status="active", created_at=1.0, updated_at=2.0)],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [
                {"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 0},
                {"chat_id": "chat-1", "user_id": "missing-user", "last_read_seq": 0},
            ],
        ),
        messages_repo=SimpleNamespace(count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {}),
        user_repo=SimpleNamespace(
            list_by_ids=lambda _user_ids: [SimpleNamespace(id="human-user-1", display_name="Human", type="human", avatar=None)],
        ),
    )

    with pytest.raises(RuntimeError, match="Chat member missing-user is not a resolvable user row"):
        service.list_conversation_summaries_for_user("human-user-1")


def test_messaging_service_conversation_summaries_fail_on_invalid_user_row_collection() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda _chat_ids: [SimpleNamespace(id="chat-1", title=None, status="active", created_at=1.0, updated_at=2.0)],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [
                {"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 0},
                {"chat_id": "chat-1", "user_id": "agent-user-1", "last_read_seq": 0},
            ],
        ),
        messages_repo=SimpleNamespace(count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {}),
        user_repo=SimpleNamespace(list_by_ids=lambda _user_ids: {"human-user-1": True}),
    )

    with pytest.raises(RuntimeError, match="User row collection is invalid"):
        service.list_conversation_summaries_for_user("human-user-1")


def test_messaging_service_conversation_summaries_fail_on_invalid_user_row() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda _chat_ids: [SimpleNamespace(id="chat-1", title=None, status="active", created_at=1.0, updated_at=2.0)],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [
                {"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 0},
                {"chat_id": "chat-1", "user_id": "agent-user-1", "last_read_seq": 0},
            ],
        ),
        messages_repo=SimpleNamespace(count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {}),
        user_repo=SimpleNamespace(list_by_ids=lambda _user_ids: ["human-user-1"]),
    )

    with pytest.raises(RuntimeError, match="User row is invalid"):
        service.list_conversation_summaries_for_user("human-user-1")


def test_messaging_service_conversation_summaries_fail_on_missing_member_user_id() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda _chat_ids: [SimpleNamespace(id="chat-1", title=None, status="active", created_at=1.0, updated_at=2.0)],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [
                {"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 0},
                {"chat_id": "chat-1", "last_read_seq": 0},
            ],
        ),
        messages_repo=SimpleNamespace(count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {}),
        user_repo=SimpleNamespace(
            list_by_ids=lambda _user_ids: [SimpleNamespace(id="human-user-1", display_name="Human", type="human", avatar=None)],
        ),
    )

    with pytest.raises(RuntimeError, match="Chat member <missing> is not a resolvable user row"):
        service.list_conversation_summaries_for_user("human-user-1")


def test_messaging_service_conversation_summaries_fail_on_unrequested_member_chat_id() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda _chat_ids: [SimpleNamespace(id="chat-1", title=None, status="active", created_at=1.0, updated_at=2.0)],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [
                {"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 0},
                {"chat_id": "chat-extra", "user_id": "agent-user-1", "last_read_seq": 0},
            ],
        ),
        messages_repo=SimpleNamespace(count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {}),
        user_repo=SimpleNamespace(
            list_by_ids=lambda _user_ids: [SimpleNamespace(id="human-user-1", display_name="Human", type="human", avatar=None)],
        ),
    )

    with pytest.raises(RuntimeError, match="Chat member row references unrequested chat chat-extra"):
        service.list_conversation_summaries_for_user("human-user-1")


def test_messaging_service_conversation_summaries_fail_when_viewer_member_row_is_missing() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda _chat_ids: [SimpleNamespace(id="chat-1", title=None, status="active", created_at=1.0, updated_at=2.0)],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [{"chat_id": "chat-1", "user_id": "agent-user-1", "last_read_seq": 0}],
        ),
        messages_repo=SimpleNamespace(count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {}),
        user_repo=SimpleNamespace(
            list_by_ids=lambda _user_ids: [SimpleNamespace(id="agent-user-1", display_name="Toad", type="agent", avatar=None)],
        ),
    )

    with pytest.raises(RuntimeError, match="Chat chat-1 is missing viewer member row human-user-1"):
        service.list_conversation_summaries_for_user("human-user-1")


def test_messaging_service_conversation_summaries_fail_when_chat_row_is_missing() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(list_by_ids=lambda _chat_ids: []),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [],
        ),
        messages_repo=SimpleNamespace(count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {}),
        user_repo=SimpleNamespace(list_by_ids=lambda _user_ids: []),
    )

    with pytest.raises(RuntimeError, match="Chat membership references missing chat row chat-1"):
        service.list_conversation_summaries_for_user("human-user-1")


def test_messaging_service_conversation_summaries_fail_on_invalid_chat_id_collection() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda chat_ids: [
                SimpleNamespace(id=chat_id, title=None, status="active", created_at=1.0, updated_at=2.0) for chat_id in chat_ids
            ],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: {"chat-1": True},
            list_members_for_chats=lambda _chat_ids: [],
        ),
        messages_repo=SimpleNamespace(count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {}),
        user_repo=SimpleNamespace(list_by_ids=lambda _user_ids: []),
    )

    with pytest.raises(RuntimeError, match="Chat id collection is invalid"):
        service.list_conversation_summaries_for_user("human-user-1")


def test_messaging_service_conversation_summaries_fail_on_invalid_member_row() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda _chat_ids: [SimpleNamespace(id="chat-1", title=None, status="active", created_at=1.0, updated_at=2.0)],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: ["chat-1"],
        ),
        messages_repo=SimpleNamespace(count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {}),
        user_repo=SimpleNamespace(list_by_ids=lambda _user_ids: []),
    )

    with pytest.raises(RuntimeError, match="Chat member row is invalid"):
        service.list_conversation_summaries_for_user("human-user-1")


def test_messaging_service_conversation_summaries_fail_on_invalid_chat_row_collection() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(list_by_ids=lambda _chat_ids: {"chat-1": True}),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [],
        ),
        messages_repo=SimpleNamespace(count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {}),
        user_repo=SimpleNamespace(list_by_ids=lambda _user_ids: []),
    )

    with pytest.raises(RuntimeError, match="Chat row collection is invalid"):
        service.list_conversation_summaries_for_user("human-user-1")


def test_messaging_service_conversation_summaries_fail_on_invalid_chat_row() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(list_by_ids=lambda _chat_ids: ["chat-1"]),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [],
        ),
        messages_repo=SimpleNamespace(count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {}),
        user_repo=SimpleNamespace(list_by_ids=lambda _user_ids: []),
    )

    with pytest.raises(RuntimeError, match="Chat row is invalid"):
        service.list_conversation_summaries_for_user("human-user-1")


def test_messaging_service_list_chats_fail_on_unrequested_latest_message_chat_id() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda _chat_ids: [SimpleNamespace(id="chat-1", title="Team", status="active", created_at=1.0, updated_at=2.0)],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [{"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 0}],
        ),
        messages_repo=SimpleNamespace(
            count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {},
            list_latest_by_chat_ids=lambda _chat_ids: {
                "chat-extra": {
                    "id": "msg-1",
                    "chat_id": "chat-extra",
                    "sender_user_id": "human-user-1",
                    "content": "wrong chat",
                    "created_at": 3.0,
                }
            },
        ),
        user_repo=SimpleNamespace(
            list_by_ids=lambda _user_ids: [SimpleNamespace(id="human-user-1", display_name="Human", type="human", avatar=None)],
        ),
    )

    with pytest.raises(RuntimeError, match="Latest message row references unrequested chat chat-extra"):
        service.list_chats_for_user("human-user-1")


def test_messaging_service_list_chats_fails_on_latest_message_missing_content() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda _chat_ids: [SimpleNamespace(id="chat-1", title="Team", status="active", created_at=1.0, updated_at=2.0)],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [{"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 0}],
        ),
        messages_repo=SimpleNamespace(
            count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {},
            list_latest_by_chat_ids=lambda _chat_ids: {
                "chat-1": {
                    "id": "msg-1",
                    "chat_id": "chat-1",
                    "sender_user_id": "human-user-1",
                    "created_at": 3.0,
                }
            },
        ),
        user_repo=SimpleNamespace(
            list_by_ids=lambda _user_ids: [SimpleNamespace(id="human-user-1", display_name="Human", type="human", avatar=None)],
        ),
    )

    with pytest.raises(RuntimeError, match="Latest message msg-1 is missing content"):
        service.list_chats_for_user("human-user-1")


def test_messaging_service_list_chats_fails_on_latest_message_invalid_content() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda _chat_ids: [SimpleNamespace(id="chat-1", title="Team", status="active", created_at=1.0, updated_at=2.0)],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [{"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 0}],
        ),
        messages_repo=SimpleNamespace(
            count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {},
            list_latest_by_chat_ids=lambda _chat_ids: {
                "chat-1": {
                    "id": "msg-1",
                    "chat_id": "chat-1",
                    "sender_user_id": "human-user-1",
                    "content": None,
                    "created_at": 3.0,
                }
            },
        ),
        user_repo=SimpleNamespace(
            list_by_ids=lambda _user_ids: [SimpleNamespace(id="human-user-1", display_name="Human", type="human", avatar=None)],
        ),
    )

    with pytest.raises(RuntimeError, match="Latest message msg-1 has invalid content"):
        service.list_chats_for_user("human-user-1")


def test_messaging_service_list_chats_fails_on_invalid_latest_message_collection() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda _chat_ids: [SimpleNamespace(id="chat-1", title="Team", status="active", created_at=1.0, updated_at=2.0)],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [{"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 0}],
        ),
        messages_repo=SimpleNamespace(
            count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {},
            list_latest_by_chat_ids=lambda _chat_ids: ["chat-1"],
        ),
        user_repo=SimpleNamespace(
            list_by_ids=lambda _user_ids: [SimpleNamespace(id="human-user-1", display_name="Human", type="human", avatar=None)],
        ),
    )

    with pytest.raises(RuntimeError, match="Latest message collection is invalid"):
        service.list_chats_for_user("human-user-1")


def test_messaging_service_list_chats_fails_on_invalid_latest_message_row() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda _chat_ids: [SimpleNamespace(id="chat-1", title="Team", status="active", created_at=1.0, updated_at=2.0)],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [{"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 0}],
        ),
        messages_repo=SimpleNamespace(
            count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {},
            list_latest_by_chat_ids=lambda _chat_ids: {"chat-1": "msg-1"},
        ),
        user_repo=SimpleNamespace(
            list_by_ids=lambda _user_ids: [SimpleNamespace(id="human-user-1", display_name="Human", type="human", avatar=None)],
        ),
    )

    with pytest.raises(RuntimeError, match="Latest message row is invalid"):
        service.list_chats_for_user("human-user-1")


def test_messaging_service_conversation_summaries_fail_without_projectable_title() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda _chat_ids: [SimpleNamespace(id="chat-1", title=None, status="active", created_at=1.0, updated_at=2.0)],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [{"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 0}],
        ),
        messages_repo=SimpleNamespace(count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {}),
        user_repo=SimpleNamespace(
            list_by_ids=lambda _user_ids: [SimpleNamespace(id="human-user-1", display_name="Human", type="human", avatar=None)],
        ),
    )

    with pytest.raises(RuntimeError, match="Chat chat-1 has no projectable title"):
        service.list_conversation_summaries_for_user("human-user-1")


def test_messaging_service_conversation_summaries_loads_users_and_unread_counts_in_parallel() -> None:
    users_started = threading.Event()
    unread_started = threading.Event()

    def _list_users(user_ids: list[str]):
        users_started.set()
        if not unread_started.wait(0.2):
            raise AssertionError("unread counts did not start while users were loading")
        return [SimpleNamespace(id=user_id, display_name=user_id, type="human", avatar=None) for user_id in user_ids]

    def _count_unread(_user_id: str, _last_read_by_chat: dict[str, int]):
        unread_started.set()
        if not users_started.wait(0.2):
            raise AssertionError("users did not start while unread counts were loading")
        return {"chat-1": 2}

    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda _chat_ids: [SimpleNamespace(id="chat-1", title=None, status="active", created_at=1.0, updated_at=2.0)],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [
                {"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 4},
                {"chat_id": "chat-1", "user_id": "agent-user-1", "last_read_seq": 0},
            ],
        ),
        messages_repo=SimpleNamespace(count_unread_by_chat_ids=_count_unread),
        user_repo=SimpleNamespace(list_by_ids=_list_users),
    )

    summaries = service.list_conversation_summaries_for_user("human-user-1")

    assert summaries[0]["unread_count"] == 2


def test_messaging_service_conversation_summaries_fail_on_invalid_unread_collection() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda _chat_ids: [SimpleNamespace(id="chat-1", title=None, status="active", created_at=1.0, updated_at=2.0)],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [
                {"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 4},
                {"chat_id": "chat-1", "user_id": "agent-user-1", "last_read_seq": 0},
            ],
        ),
        messages_repo=SimpleNamespace(count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: ["chat-1"]),
        user_repo=SimpleNamespace(
            list_by_ids=lambda user_ids: [
                SimpleNamespace(id=user_id, display_name=user_id, type="human", avatar=None) for user_id in user_ids
            ]
        ),
    )

    with pytest.raises(RuntimeError, match="Unread count collection is invalid"):
        service.list_conversation_summaries_for_user("human-user-1")


def test_messaging_service_conversation_summaries_fail_on_invalid_unread_value() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda _chat_ids: [SimpleNamespace(id="chat-1", title=None, status="active", created_at=1.0, updated_at=2.0)],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [
                {"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 4},
                {"chat_id": "chat-1", "user_id": "agent-user-1", "last_read_seq": 0},
            ],
        ),
        messages_repo=SimpleNamespace(count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {"chat-1": None}),
        user_repo=SimpleNamespace(
            list_by_ids=lambda user_ids: [
                SimpleNamespace(id=user_id, display_name=user_id, type="human", avatar=None) for user_id in user_ids
            ]
        ),
    )

    with pytest.raises(RuntimeError, match="Unread count for chat chat-1 is invalid"):
        service.list_conversation_summaries_for_user("human-user-1")


def test_messaging_service_conversation_summaries_fail_on_unrequested_unread_chat_id() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda _chat_ids: [SimpleNamespace(id="chat-1", title=None, status="active", created_at=1.0, updated_at=2.0)],
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members_for_chats=lambda _chat_ids: [
                {"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 4},
                {"chat_id": "chat-1", "user_id": "agent-user-1", "last_read_seq": 0},
            ],
        ),
        messages_repo=SimpleNamespace(count_unread_by_chat_ids=lambda _user_id, _last_read_by_chat: {"chat-extra": 3}),
        user_repo=SimpleNamespace(
            list_by_ids=lambda user_ids: [
                SimpleNamespace(id=user_id, display_name=user_id, type="human", avatar=None) for user_id in user_ids
            ]
        ),
    )

    with pytest.raises(RuntimeError, match="Unread count row references unrequested chat chat-extra"):
        service.list_conversation_summaries_for_user("human-user-1")


def test_messaging_service_get_chat_detail_exposes_agent_user_participant_id() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(
            list_members=lambda _chat_id: [{"user_id": "human-user-1"}, {"user_id": "agent-user-1"}],
        ),
        messages_repo=SimpleNamespace(),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None)
                if uid == "human-user-1"
                else SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None)
                if uid == "agent-user-1"
                else None
            )
        ),
    )

    detail = service.get_chat_detail(
        SimpleNamespace(
            id="chat-1",
            title="Chat title",
            status="active",
            created_by_user_id="human-user-1",
            created_at="2026-04-07T00:00:00Z",
        )
    )

    assert detail == {
        "id": "chat-1",
        "title": "Chat title",
        "status": "active",
        "created_by_user_id": "human-user-1",
        "created_at": "2026-04-07T00:00:00Z",
        "members": [
            {
                "id": "human-user-1",
                "name": "Human",
                "type": "human",
                "avatar_url": avatar_url("human-user-1", False),
            },
            {
                "id": "agent-user-1",
                "name": "Toad",
                "type": "agent",
                "avatar_url": avatar_url("agent-user-1", False),
            },
        ],
    }


def test_messaging_service_mark_read_resets_unread_count_via_last_read_seq_watermark() -> None:
    class _StatefulChatMemberRepo:
        def __init__(self) -> None:
            self._rows = {("chat-1", "human-user-1"): {"last_read_seq": 1}}

        def list_chats_for_user(self, _user_id: str) -> list[str]:
            return ["chat-1"]

        def list_members_for_chats(self, _chat_ids: list[str]) -> list[dict[str, Any]]:
            return [
                {"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": self.last_read_seq("chat-1", "human-user-1")},
                {"chat_id": "chat-1", "user_id": "agent-user-1", "last_read_seq": 0},
            ]

        def update_last_read(self, chat_id: str, user_id: str, last_read_seq: int) -> None:
            self._rows[(chat_id, user_id)] = {"last_read_seq": last_read_seq}

        def last_read_seq(self, chat_id: str, user_id: str) -> int:
            return int(self._rows[(chat_id, user_id)]["last_read_seq"])

    class _StatefulMessagesRepo:
        def __init__(self, members_repo: _StatefulChatMemberRepo) -> None:
            self._members_repo = members_repo
            self._rows = [
                {
                    "id": "msg-1",
                    "chat_id": "chat-1",
                    "seq": 1,
                    "sender_user_id": "human-user-1",
                    "content": "ping",
                    "created_at": "2026-04-07T00:00:00Z",
                },
                {
                    "id": "msg-2",
                    "chat_id": "chat-1",
                    "seq": 2,
                    "sender_user_id": "agent-user-1",
                    "content": "READ_WATERMARK_OK",
                    "created_at": "2026-04-07T00:00:01Z",
                },
            ]

        def list_latest_by_chat_ids(self, _chat_ids: list[str]) -> dict[str, dict[str, Any]]:
            return {"chat-1": self._rows[-1]}

        def list_by_chat(self, _chat_id: str, limit: int = 50, viewer_id: str | None = None) -> list[dict[str, Any]]:
            del viewer_id
            return self._rows[-limit:]

        def count_unread_by_chat_ids(self, user_id: str, last_read_by_chat: dict[str, int]) -> dict[str, int]:
            return {
                chat_id: sum(
                    1
                    for row in self._rows
                    if row["chat_id"] == chat_id and row["sender_user_id"] != user_id and int(row["seq"]) > last_read_seq
                )
                for chat_id, last_read_seq in last_read_by_chat.items()
            }

    members_repo = _StatefulChatMemberRepo()
    messages_repo = _StatefulMessagesRepo(members_repo)
    service = MessagingService(
        chat_repo=SimpleNamespace(
            list_by_ids=lambda chat_ids: [
                SimpleNamespace(id=chat_id, title=None, status="active", created_at="2026-04-07T00:00:00Z", updated_at=None)
                for chat_id in chat_ids
            ]
        ),
        chat_member_repo=members_repo,
        messages_repo=messages_repo,
        user_repo=SimpleNamespace(
            list_by_ids=lambda user_ids: [
                SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None)
                if uid == "human-user-1"
                else SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None)
                if uid == "agent-user-1"
                else None
                for uid in user_ids
            ]
        ),
    )

    before = service.list_chats_for_user("human-user-1")

    assert before[0]["unread_count"] == 1

    service.mark_read("chat-1", "human-user-1")

    after = service.list_chats_for_user("human-user-1")

    assert after[0]["unread_count"] == 0


def test_chat_tool_formats_agent_user_id_sender_as_agent_name() -> None:
    registry = ToolRegistry()
    service = ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(),
    )

    rendered = service._format_msgs([{"sender_id": "agent-user-1", "content": "hello"}], "human-user-1")

    assert "[Toad]: hello" in rendered


def test_read_messages_fails_before_mark_read_on_unknown_message_sender() -> None:
    registry = ToolRegistry()
    marked: list[tuple[str, str]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_messages_by_time_range=lambda _chat_id, *, after=None, before=None: [
                {
                    "sender_id": "missing-user",
                    "content": f"after={after};before={before}",
                }
            ],
            mark_read=lambda chat_id, user_id: marked.append((chat_id, user_id)),
        ),
    )

    read_messages = registry.get("read_messages")
    assert read_messages is not None

    with pytest.raises(RuntimeError) as excinfo:
        read_messages.handler(chat_id="chat-1", range="-1h:")

    assert str(excinfo.value) == "Chat message sender identity not found: missing-user"
    assert marked == []


def test_read_messages_fails_before_mark_read_on_invalid_message_row() -> None:
    registry = ToolRegistry()
    marked: list[tuple[str, str]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_messages_by_time_range=lambda _chat_id, *, after=None, before=None: ["message-1"],
            mark_read=lambda chat_id, user_id: marked.append((chat_id, user_id)),
        ),
    )

    read_messages = registry.get("read_messages")
    assert read_messages is not None

    with pytest.raises(RuntimeError) as excinfo:
        read_messages.handler(chat_id="chat-1", range="-1h:")

    assert str(excinfo.value) == "Chat message row is invalid"
    assert marked == []


def test_read_messages_fails_before_mark_read_on_invalid_history_collection() -> None:
    registry = ToolRegistry()
    marked: list[tuple[str, str]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_messages_by_time_range=lambda _chat_id, *, after=None, before=None: {"sender_id": "agent-user-1"},
            mark_read=lambda chat_id, user_id: marked.append((chat_id, user_id)),
        ),
    )

    read_messages = registry.get("read_messages")
    assert read_messages is not None

    with pytest.raises(RuntimeError) as excinfo:
        read_messages.handler(chat_id="chat-1", range="-1h:")

    assert str(excinfo.value) == "Chat message collection is invalid"
    assert marked == []


def test_read_messages_fails_before_mark_read_on_invalid_unread_collection() -> None:
    registry = ToolRegistry()
    marked: list[tuple[str, str]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_unread=lambda _chat_id, _user_id: {"sender_id": "agent-user-1"},
            mark_read=lambda chat_id, user_id: marked.append((chat_id, user_id)),
        ),
    )

    read_messages = registry.get("read_messages")
    assert read_messages is not None

    with pytest.raises(RuntimeError) as excinfo:
        read_messages.handler(chat_id="chat-1")

    assert str(excinfo.value) == "Chat message collection is invalid"
    assert marked == []


def test_read_messages_fails_before_mark_read_on_missing_message_content() -> None:
    registry = ToolRegistry()
    marked: list[tuple[str, str]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_messages_by_time_range=lambda _chat_id, *, after=None, before=None: [
                {
                    "sender_id": "agent-user-1",
                }
            ],
            mark_read=lambda chat_id, user_id: marked.append((chat_id, user_id)),
        ),
    )

    read_messages = registry.get("read_messages")
    assert read_messages is not None

    with pytest.raises(RuntimeError) as excinfo:
        read_messages.handler(chat_id="chat-1", range="-1h:")

    assert str(excinfo.value) == "Chat message from agent-user-1 is missing content"
    assert marked == []


def test_read_messages_fails_before_mark_read_on_invalid_message_content() -> None:
    registry = ToolRegistry()
    marked: list[tuple[str, str]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_messages_by_time_range=lambda _chat_id, *, after=None, before=None: [
                {
                    "sender_id": "agent-user-1",
                    "content": None,
                }
            ],
            mark_read=lambda chat_id, user_id: marked.append((chat_id, user_id)),
        ),
    )

    read_messages = registry.get("read_messages")
    assert read_messages is not None

    with pytest.raises(RuntimeError) as excinfo:
        read_messages.handler(chat_id="chat-1", range="-1h:")

    assert str(excinfo.value) == "Chat message from agent-user-1 has invalid content"
    assert marked == []


def test_chat_tool_send_accepts_agent_user_target_id() -> None:
    registry = ToolRegistry()
    sent: list[tuple[str, str, str]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            find_or_create_chat=lambda user_ids: {"id": "chat-1", "user_ids": user_ids},
            count_unread=lambda _chat_id, _user_id: 0,
            send=lambda chat_id, sender_id, content, **_kwargs: sent.append((chat_id, sender_id, content)),
        ),
    )

    send_message = registry.get("send_message")
    assert send_message is not None

    result = send_message.handler(content="hello", participant_id="agent-user-1")

    assert result == "Message sent to Toad."
    assert sent == [("chat-1", "human-user-1", "hello")]


def test_chat_tool_send_fails_before_unread_check_when_created_chat_is_missing_id() -> None:
    registry = ToolRegistry()
    unread_checks: list[tuple[str, str]] = []
    sent: list[tuple[str, str, str]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            find_or_create_chat=lambda _user_ids: {"user_ids": ["human-user-1", "agent-user-1"]},
            count_unread=lambda chat_id, user_id: unread_checks.append((chat_id, user_id)) or 0,
            send=lambda chat_id, sender_id, content, **_kwargs: sent.append((chat_id, sender_id, content)),
        ),
    )

    send_message = registry.get("send_message")
    assert send_message is not None

    with pytest.raises(RuntimeError) as excinfo:
        send_message.handler(content="hello", participant_id="agent-user-1")

    assert str(excinfo.value) == "Created direct chat is missing id"
    assert unread_checks == []
    assert sent == []


def test_chat_tool_send_fails_before_unread_check_when_created_chat_row_is_invalid() -> None:
    registry = ToolRegistry()
    unread_checks: list[tuple[str, str]] = []
    sent: list[tuple[str, str, str]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            find_or_create_chat=lambda _user_ids: "chat-1",
            count_unread=lambda chat_id, user_id: unread_checks.append((chat_id, user_id)) or 0,
            send=lambda chat_id, sender_id, content, **_kwargs: sent.append((chat_id, sender_id, content)),
        ),
    )

    send_message = registry.get("send_message")
    assert send_message is not None

    with pytest.raises(RuntimeError) as excinfo:
        send_message.handler(content="hello", participant_id="agent-user-1")

    assert str(excinfo.value) == "Created direct chat row is invalid"
    assert unread_checks == []
    assert sent == []


def test_chat_tool_send_fails_before_unread_check_when_created_chat_id_is_empty() -> None:
    registry = ToolRegistry()
    unread_checks: list[tuple[str, str]] = []
    sent: list[tuple[str, str, str]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            find_or_create_chat=lambda _user_ids: {"id": ""},
            count_unread=lambda chat_id, user_id: unread_checks.append((chat_id, user_id)) or 0,
            send=lambda chat_id, sender_id, content, **_kwargs: sent.append((chat_id, sender_id, content)),
        ),
    )

    send_message = registry.get("send_message")
    assert send_message is not None

    with pytest.raises(RuntimeError) as excinfo:
        send_message.handler(content="hello", participant_id="agent-user-1")

    assert str(excinfo.value) == "Created direct chat has invalid id"
    assert unread_checks == []
    assert sent == []


def test_chat_tool_send_fails_before_send_when_unread_count_is_invalid() -> None:
    registry = ToolRegistry()
    sent: list[tuple[str, str, str]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            find_or_create_chat=lambda _user_ids: {"id": "chat-1"},
            count_unread=lambda _chat_id, _user_id: None,
            send=lambda chat_id, sender_id, content, **_kwargs: sent.append((chat_id, sender_id, content)),
        ),
    )

    send_message = registry.get("send_message")
    assert send_message is not None

    with pytest.raises(RuntimeError) as excinfo:
        send_message.handler(content="hello", participant_id="agent-user-1")

    assert str(excinfo.value) == "Chat unread count is invalid for chat chat-1"
    assert sent == []


def test_chat_tool_send_appends_yield_signal_to_content_and_payload() -> None:
    registry = ToolRegistry()
    sent: list[dict[str, object]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=SimpleNamespace(
            is_chat_member=lambda _chat_id, _user_id: True,
            count_unread=lambda _chat_id, _user_id: 0,
            send=lambda chat_id, sender_id, content, **kwargs: sent.append(
                {
                    "chat_id": chat_id,
                    "sender_id": sender_id,
                    "content": content,
                    **kwargs,
                }
            ),
        ),
    )

    send_message = registry.get("send_message")
    assert send_message is not None

    result = send_message.handler(content="done", chat_id="chat-1", signal="yield")

    assert result == "Message sent to chat."
    assert sent == [
        {
            "chat_id": "chat-1",
            "sender_id": "human-user-1",
            "content": "done\n[signal: yield]",
            "enforce_caught_up": True,
            "mentions": None,
            "signal": "yield",
        }
    ]


def test_chat_tool_send_checks_group_membership_via_messaging_service_without_member_repo() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=SimpleNamespace(
            is_chat_member=lambda _chat_id, _user_id: False,
        ),
    )

    send_message = registry.get("send_message")
    assert send_message is not None

    with pytest.raises(RuntimeError, match="You are not a member of chat chat-1"):
        send_message.handler(content="hello", chat_id="chat-1")


def test_chat_tool_send_requires_group_reply_to_consume_peer_unread() -> None:
    registry = ToolRegistry()
    sent: list[dict[str, object]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="agent-user-1",
        messaging_service=SimpleNamespace(
            is_chat_member=lambda _chat_id, _user_id: True,
            count_unread=lambda _chat_id, _user_id: 1,
            send=lambda chat_id, sender_id, content, **kwargs: sent.append(
                {
                    "chat_id": chat_id,
                    "sender_id": sender_id,
                    "content": content,
                    **kwargs,
                }
            ),
        ),
    )

    send_message = registry.get("send_message")
    assert send_message is not None

    result = send_message.handler(content="GROUP_READ_OK", chat_id="chat-1")

    assert isinstance(result, ToolResultEnvelope)
    assert result.kind == "error"
    assert result.metadata["error_type"] == "chat_not_caught_up"
    assert result.content == "You have 1 unread message(s). Call read_messages(chat_id='chat-1') first."
    assert sent == []


def test_chat_tool_send_returns_tool_error_when_chat_advances_after_read() -> None:
    registry = ToolRegistry()

    def _send(*_args, **_kwargs):
        raise RuntimeError("Chat advanced after your last read. Call read_messages(chat_id='chat-1') first.")

    ChatToolService(
        registry=registry,
        chat_identity_id="agent-user-1",
        messaging_service=SimpleNamespace(
            is_chat_member=lambda _chat_id, _user_id: True,
            count_unread=lambda _chat_id, _user_id: 0,
            send=_send,
        ),
    )

    send_message = registry.get("send_message")
    assert send_message is not None

    result = send_message.handler(content="GROUP_READ_OK", chat_id="chat-1")

    assert isinstance(result, ToolResultEnvelope)
    assert result.kind == "error"
    assert result.metadata["error_type"] == "chat_not_caught_up"
    assert result.content == "Chat advanced after your last read. Call read_messages(chat_id='chat-1') first."


def test_read_messages_uses_agent_user_target_name_on_no_history() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(find_direct_chat_id=lambda _eid, _user_id: None),
    )

    read_messages = registry.get("read_messages")
    assert read_messages is not None

    result = read_messages.handler(participant_id="agent-user-1")

    assert result == "No chat history with Toad."


def test_read_messages_uses_messaging_service_direct_chat_lookup_without_member_repo() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            find_direct_chat_id=lambda _eid, _user_id: None,
        ),
    )

    read_messages = registry.get("read_messages")
    assert read_messages is not None

    result = read_messages.handler(participant_id="agent-user-1")

    assert result == "No chat history with Toad."


def test_read_messages_uses_messaging_service_time_range_history_without_messages_repo() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            list_messages_by_time_range=lambda _chat_id, *, after=None, before=None: [
                {
                    "sender_id": "agent-user-1",
                    "content": f"after={after};before={before}",
                }
            ],
            mark_read=lambda *_args, **_kwargs: None,
        ),
    )

    read_messages = registry.get("read_messages")
    assert read_messages is not None

    result = read_messages.handler(chat_id="chat-1", range="-1h:")

    assert "[Toad]: after=" in result


def test_chat_tool_search_requires_direct_chat_for_agent_user_target() -> None:
    registry = ToolRegistry()
    search_calls: list[tuple[str, str | None]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            find_direct_chat_id=lambda _eid, _user_id: None,
            search_messages=lambda query, *, chat_id=None: search_calls.append((query, chat_id)) or [{"content": "wrong"}],
        ),
    )

    search_messages = registry.get("search_messages")
    assert search_messages is not None

    result = search_messages.handler(query="hello", participant_id="agent-user-1")

    assert result == "No messages matching 'hello' with Toad."
    assert search_calls == []


def test_chat_tool_search_uses_messaging_service_direct_chat_lookup_without_member_repo() -> None:
    registry = ToolRegistry()
    search_calls: list[tuple[str, str | None]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            find_direct_chat_id=lambda _eid, _user_id: "chat-1",
            search_messages=lambda query, *, chat_id=None: search_calls.append((query, chat_id)) or [],
        ),
    )

    search_messages = registry.get("search_messages")
    assert search_messages is not None

    result = search_messages.handler(query="hello", participant_id="agent-user-1")

    assert result == "No messages matching 'hello'."
    assert search_calls == [("hello", "chat-1")]


def test_chat_tool_search_fails_on_unknown_message_sender() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            search_messages=lambda _query, *, chat_id=None: [{"sender_id": "missing-user", "content": f"chat_id={chat_id}"}],
        ),
    )

    search_messages = registry.get("search_messages")
    assert search_messages is not None

    with pytest.raises(RuntimeError) as excinfo:
        search_messages.handler(query="hello")

    assert str(excinfo.value) == "Chat message sender identity not found: missing-user"


def test_chat_tool_search_fails_on_invalid_message_row() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            search_messages=lambda _query, *, chat_id=None: ["message-1"],
        ),
    )

    search_messages = registry.get("search_messages")
    assert search_messages is not None

    with pytest.raises(RuntimeError) as excinfo:
        search_messages.handler(query="hello")

    assert str(excinfo.value) == "Chat search message row is invalid"


def test_chat_tool_search_fails_on_invalid_result_collection() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            search_messages=lambda _query, *, chat_id=None: {"sender_id": "agent-user-1"},
        ),
    )

    search_messages = registry.get("search_messages")
    assert search_messages is not None

    with pytest.raises(RuntimeError) as excinfo:
        search_messages.handler(query="hello")

    assert str(excinfo.value) == "Chat search result collection is invalid"


def test_chat_tool_search_fails_on_missing_message_content() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            search_messages=lambda _query, *, chat_id=None: [{"sender_id": "agent-user-1"}],
        ),
    )

    search_messages = registry.get("search_messages")
    assert search_messages is not None

    with pytest.raises(RuntimeError) as excinfo:
        search_messages.handler(query="hello")

    assert str(excinfo.value) == "Chat search message from agent-user-1 is missing content"


def test_chat_tool_search_fails_on_invalid_message_content() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        messaging_service=_messaging_display_service(
            search_messages=lambda _query, *, chat_id=None: [{"sender_id": "agent-user-1", "content": None}],
        ),
    )

    search_messages = registry.get("search_messages")
    assert search_messages is not None

    with pytest.raises(RuntimeError) as excinfo:
        search_messages.handler(query="hello")

    assert str(excinfo.value) == "Chat search message from agent-user-1 has invalid content"


def test_deliver_to_agents_routes_delivery_by_agent_user_id() -> None:
    delivered: list[tuple[str, str]] = []
    dispatcher = ChatDeliveryDispatcher(
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: [{"user_id": "agent-user-1"}]),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None)
                if uid == "agent-user-1"
                else SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None)
            )
        ),
        unread_counter=lambda _chat_id, _user_id: 0,
        delivery_fn=lambda request: delivered.append((request.recipient_id, request.recipient_user.id)),
    )

    dispatcher.dispatch("chat-1", "human-user-1", "hello", [])

    assert delivered == [("agent-user-1", "agent-user-1")]


def test_same_owner_group_chat_kickoff_delivers_without_relationship() -> None:
    delivered: list[tuple[str, str]] = []
    resolver = HireVisitDeliveryResolver(
        contact_repo=SimpleNamespace(get=lambda _owner_id, _target_id: None),
        chat_member_repo=SimpleNamespace(
            list_members=lambda _chat_id: [
                {"user_id": "human-user-1"},
                {"user_id": "agent-user-1"},
                {"user_id": "agent-user-2"},
            ]
        ),
        relationship_repo=SimpleNamespace(get=lambda _a, _b: None),
    )
    dispatcher = ChatDeliveryDispatcher(
        chat_member_repo=SimpleNamespace(
            list_members=lambda _chat_id: [
                {"user_id": "human-user-1"},
                {"user_id": "agent-user-1"},
                {"user_id": "agent-user-2"},
            ]
        ),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None, owner_user_id=None)
                if uid == "human-user-1"
                else SimpleNamespace(id=uid, display_name="Morel", type="agent", avatar=None, owner_user_id="human-user-1")
                if uid == "agent-user-1"
                else SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None, owner_user_id="human-user-1")
                if uid == "agent-user-2"
                else None
            )
        ),
        unread_counter=lambda _chat_id, _user_id: 0,
        delivery_resolver=resolver,
        delivery_fn=lambda request: delivered.append((request.recipient_id, request.recipient_user.id)),
    )

    dispatcher.dispatch("chat-1", "human-user-1", "hello", [])

    assert delivered == [("agent-user-1", "agent-user-1"), ("agent-user-2", "agent-user-2")]


def test_delivery_resolver_drops_when_new_contact_edge_is_blocked() -> None:
    resolver = HireVisitDeliveryResolver(
        contact_repo=SimpleNamespace(
            get=lambda _owner_id, _target_id: {
                "source_user_id": "thread-user-1",
                "target_user_id": "human-user-1",
                "kind": "normal",
                "state": "active",
                "blocked": True,
                "muted": False,
            }
        ),
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: []),
        relationship_repo=None,
    )

    action = resolver.resolve("thread-user-1", "chat-1", "human-user-1")

    assert action is DeliveryAction.DROP


def test_delivery_resolver_reads_contact_edge_row_objects() -> None:
    resolver = HireVisitDeliveryResolver(
        contact_repo=SimpleNamespace(
            get=lambda _owner_id, _target_id: ContactEdgeRow(
                source_user_id="agent-user-1",
                target_user_id="human-user-1",
                kind="normal",
                state="active",
                muted=False,
                blocked=False,
                created_at=1.0,
            )
        ),
        chat_member_repo=SimpleNamespace(
            list_members=lambda _chat_id: [
                {"user_id": "agent-user-1", "muted": False},
                {"user_id": "human-user-1", "muted": False},
            ]
        ),
        relationship_repo=None,
    )

    action = resolver.resolve("agent-user-1", "chat-1", "human-user-1")

    assert action is DeliveryAction.DELIVER


def test_delivery_resolver_propagates_contact_repo_failures() -> None:
    def _raise_get(_owner_id: str, _target_id: str) -> None:
        raise RuntimeError("contact repo unavailable")

    resolver = HireVisitDeliveryResolver(
        contact_repo=SimpleNamespace(get=_raise_get),
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: []),
        relationship_repo=None,
    )

    with pytest.raises(RuntimeError):
        resolver.resolve("agent-user-1", "chat-1", "human-user-1")


def test_delivery_resolver_fails_on_invalid_existing_relationship_row() -> None:
    resolver = HireVisitDeliveryResolver(
        contact_repo=SimpleNamespace(get=lambda _owner_id, _target_id: None),
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: []),
        relationship_repo=SimpleNamespace(
            get=lambda _recipient_id, _sender_id: {
                "id": "hire_visit:agent-user-1:human-user-1",
                "user_low": "agent-user-1",
                "user_high": "human-user-1",
                "kind": "hire_visit",
                "created_at": "2026-04-07T00:00:00Z",
                "updated_at": "2026-04-07T00:00:01Z",
            }
        ),
    )

    with pytest.raises(RuntimeError, match="Invalid relationship row hire_visit:agent-user-1:human-user-1"):
        resolver.resolve("agent-user-1", "chat-1", "human-user-1")


def test_delivery_resolver_requires_current_chat_member_contract() -> None:
    resolver = HireVisitDeliveryResolver(
        contact_repo=SimpleNamespace(get=lambda _owner_id, _target_id: None),
        chat_member_repo=SimpleNamespace(),
        relationship_repo=None,
    )

    with pytest.raises(AttributeError):
        resolver.resolve("agent-user-1", "chat-1", "human-user-1")


def test_delivery_resolver_fails_on_chat_member_row_missing_user_id() -> None:
    resolver = HireVisitDeliveryResolver(
        contact_repo=SimpleNamespace(get=lambda _owner_id, _target_id: None),
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: [{}]),
        relationship_repo=None,
    )

    with pytest.raises(RuntimeError, match="Chat mute member row is missing user_id in chat chat-1"):
        resolver.resolve("agent-user-1", "chat-1", "human-user-1")


def test_delivery_resolver_fails_when_recipient_membership_is_missing() -> None:
    resolver = HireVisitDeliveryResolver(
        contact_repo=SimpleNamespace(get=lambda _owner_id, _target_id: None),
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: [{"user_id": "human-user-1"}]),
        relationship_repo=None,
    )

    with pytest.raises(RuntimeError, match="Chat chat-1 is missing delivery recipient member row agent-user-1"):
        resolver.resolve("agent-user-1", "chat-1", "human-user-1")


def test_delivery_resolver_notifies_when_new_contact_edge_is_muted() -> None:
    resolver = HireVisitDeliveryResolver(
        contact_repo=SimpleNamespace(
            get=lambda _owner_id, _target_id: {
                "source_user_id": "thread-user-1",
                "target_user_id": "human-user-1",
                "kind": "normal",
                "state": "active",
                "blocked": False,
                "muted": True,
            }
        ),
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: []),
        relationship_repo=None,
    )

    action = resolver.resolve("thread-user-1", "chat-1", "human-user-1")

    assert action is DeliveryAction.NOTIFY


def test_same_owner_agent_turn_delivers_to_sibling_user_without_relationship() -> None:
    delivered: list[tuple[str, str]] = []
    resolver = HireVisitDeliveryResolver(
        contact_repo=SimpleNamespace(get=lambda _owner_id, _target_id: None),
        chat_member_repo=SimpleNamespace(
            list_members=lambda _chat_id: [
                {"user_id": "human-user-1"},
                {"user_id": "agent-user-1"},
                {"user_id": "agent-user-2"},
            ]
        ),
        relationship_repo=SimpleNamespace(get=lambda _a, _b: None),
    )
    dispatcher = ChatDeliveryDispatcher(
        chat_member_repo=SimpleNamespace(
            list_members=lambda _chat_id: [
                {"user_id": "human-user-1"},
                {"user_id": "agent-user-1"},
                {"user_id": "agent-user-2"},
            ]
        ),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None, owner_user_id=None)
                if uid == "human-user-1"
                else SimpleNamespace(id=uid, display_name="Morel", type="agent", avatar=None, owner_user_id="human-user-1")
                if uid == "agent-user-1"
                else SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None, owner_user_id="human-user-1")
                if uid == "agent-user-2"
                else None
            )
        ),
        unread_counter=lambda _chat_id, _user_id: 0,
        delivery_resolver=resolver,
        delivery_fn=lambda request: delivered.append((request.recipient_id, request.recipient_user.id)),
    )

    dispatcher.dispatch("chat-1", "agent-user-1", "hello", [])

    assert delivered == [("agent-user-2", "agent-user-2")]


@pytest.mark.asyncio
async def test_agent_runtime_gateway_uses_recipient_social_user_id_for_thread_lookup_and_passes_through_envelope_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started, unread_calls, enqueued = await _run_chat_delivery(monkeypatch, chat_id="chat-1", unread_count=7)

    assert started == [("thread-1", "chat-1", "agent-user-1")]
    assert unread_calls == []
    assert enqueued == [("Human|chat-1|7|ping", "thread-1", "human-user-1", "Human")]


@pytest.mark.asyncio
async def test_recipient_thread_resolution_requires_current_thread_repo_contract() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(
                get_by_user_id=lambda uid: {"id": "thread-1", "agent_user_id": "agent-user-1"} if uid == "agent-user-1" else None,
                get_by_id=lambda thread_id: {"id": thread_id, "agent_user_id": "agent-user-1"} if thread_id == "thread-1" else None,
            ),
            agent_pool={},
            queue_manager=SimpleNamespace(enqueue=lambda *_args, **_kwargs: None),
            thread_cwd={},
            thread_sandbox={},
            thread_tasks={},
            thread_locks={},
            thread_locks_guard=asyncio.Lock(),
        )
    )
    runtime_state = build_agent_runtime_state(app, typing_tracker=SimpleNamespace(start_chat=lambda *_args, **_kwargs: None))
    gateway = runtime_state.gateway
    app.state.threads_runtime_state = SimpleNamespace(
        agent_runtime_gateway=gateway,
        activity_reader=runtime_state.activity_reader,
    )

    with pytest.raises(AttributeError):
        await asyncio.to_thread(
            chat_delivery_hook.make_chat_delivery_fn(
                app,
                activity_reader=runtime_state.activity_reader,
                thread_repo=app.state.thread_repo,
            ),
            ChatDeliveryRequest(
                recipient_id="agent-user-1",
                recipient_user=SimpleNamespace(id="agent-user-1", type="agent"),
                content="hello",
                sender_name="Human",
                sender_type="human",
                chat_id="chat-1",
                sender_id="human-user-1",
                sender_avatar_url=None,
                unread_count=1,
                signal="ping",
            ),
        )


async def _run_chat_delivery(
    monkeypatch: pytest.MonkeyPatch,
    *,
    threads: list[dict[str, Any]] | None = None,
    pool: dict[str, Any] | None = None,
    chat_id: str,
    unread_count: int,
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]], list[tuple[str, str, str | None, str | None]]]:
    started: list[tuple[str, str, str]] = []
    unread_calls: list[tuple[str, str]] = []
    enqueued: list[tuple[str, str, str | None, str | None]] = []

    async def _fake_get_or_create_agent(_app, _sandbox_type: str, *, thread_id: str):
        return SimpleNamespace(id=f"agent-for-{thread_id}")

    monkeypatch.setattr("backend.threads.chat_adapters.bootstrap.get_or_create_agent", _fake_get_or_create_agent)
    monkeypatch.setattr("backend.threads.chat_adapters.bootstrap.resolve_thread_sandbox", lambda _app, _thread_id: "local")
    monkeypatch.setattr("backend.threads.chat_adapters.bootstrap._ensure_thread_handlers", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "backend.threads.chat_adapters.chat_inlet.format_chat_notification",
        lambda sender_name, chat_id, unread_count, signal=None: f"{sender_name}|{chat_id}|{unread_count}|{signal}",
    )

    thread_rows = threads or [{"id": "thread-1", "agent_user_id": "agent-user-1", "is_main": True, "branch_index": 0}]
    default_thread = next((row for row in thread_rows if row.get("is_main")), thread_rows[0])
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(
                get_by_user_id=lambda uid: default_thread if uid == "agent-user-1" else None,
                list_by_agent_user=lambda uid: list(thread_rows) if uid == "agent-user-1" else [],
                get_by_id=lambda thread_id: next((row for row in thread_rows if row["id"] == thread_id), None),
            ),
            agent_pool=pool or {},
            queue_manager=SimpleNamespace(
                enqueue=lambda content, thread_id, notification_type, **meta: enqueued.append(
                    (content, thread_id, meta.get("sender_id"), meta.get("sender_name"))
                )
            ),
            thread_cwd={},
            thread_sandbox={},
            thread_tasks={},
            thread_locks={},
            thread_locks_guard=asyncio.Lock(),
        )
    )
    runtime_state = build_agent_runtime_state(
        app,
        typing_tracker=SimpleNamespace(start_chat=lambda thread_id, chat_id, user_id: started.append((thread_id, chat_id, user_id))),
    )
    gateway = runtime_state.gateway
    app.state.threads_runtime_state = SimpleNamespace(
        agent_runtime_gateway=gateway,
        activity_reader=runtime_state.activity_reader,
    )

    await asyncio.to_thread(
        chat_delivery_hook.make_chat_delivery_fn(
            app,
            activity_reader=runtime_state.activity_reader,
            thread_repo=app.state.thread_repo,
        ),
        ChatDeliveryRequest(
            recipient_id="agent-user-1",
            recipient_user=SimpleNamespace(id="agent-user-1", type="agent"),
            content="hello",
            sender_name="Human",
            sender_type="human",
            chat_id=chat_id,
            sender_id="human-user-1",
            sender_avatar_url=None,
            unread_count=unread_count,
            signal="ping",
        ),
    )

    return started, unread_calls, enqueued


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("threads", "pool", "chat_id", "unread_count", "expected_thread_id"),
    [
        (
            [
                {"id": "thread-main", "agent_user_id": "agent-user-1", "is_main": True, "branch_index": 0},
                {"id": "thread-child", "agent_user_id": "agent-user-1", "is_main": False, "branch_index": 1},
            ],
            {
                "thread-main:local": SimpleNamespace(runtime=SimpleNamespace(current_state=AgentState.IDLE)),
                "thread-child:local": SimpleNamespace(runtime=SimpleNamespace(current_state=AgentState.ACTIVE)),
            },
            "chat-2",
            3,
            "thread-child",
        ),
        (
            [
                {"id": "thread-main", "agent_user_id": "agent-user-1", "is_main": True, "branch_index": 0},
                {"id": "thread-child", "agent_user_id": "agent-user-1", "is_main": False, "branch_index": 1},
            ],
            {
                "thread-main:local": SimpleNamespace(runtime=SimpleNamespace(current_state=AgentState.IDLE)),
                "thread-child:local": SimpleNamespace(runtime=SimpleNamespace(current_state=AgentState.READY)),
            },
            "chat-3",
            1,
            "thread-child",
        ),
        (
            [
                {"id": "thread-main", "agent_user_id": "agent-user-1", "is_main": True, "branch_index": 0},
                {"id": "thread-child", "agent_user_id": "agent-user-1", "is_main": False, "branch_index": 1},
            ],
            {
                "thread-main:local": SimpleNamespace(runtime=SimpleNamespace(current_state=AgentState.ACTIVE)),
                "thread-child:local": SimpleNamespace(runtime=SimpleNamespace(current_state=AgentState.READY)),
            },
            "chat-4",
            1,
            "thread-child",
        ),
        (
            [
                {"id": "thread-main", "agent_user_id": "agent-user-1", "is_main": True, "branch_index": 0},
                {"id": "thread-child-old", "agent_user_id": "agent-user-1", "is_main": False, "branch_index": 1},
                {"id": "thread-child-fresh", "agent_user_id": "agent-user-1", "is_main": False, "branch_index": 2},
            ],
            {
                "thread-main:local": SimpleNamespace(runtime=SimpleNamespace(current_state=AgentState.ACTIVE)),
                "thread-child-old:local": SimpleNamespace(runtime=SimpleNamespace(current_state=AgentState.IDLE)),
                "thread-child-fresh:local": SimpleNamespace(runtime=SimpleNamespace(current_state=AgentState.READY)),
            },
            "chat-5",
            1,
            "thread-child-fresh",
        ),
    ],
    ids=["active-child-main-idle", "ready-child-main-idle", "ready-child-active-main", "latest-live-child"],
)
async def test_agent_runtime_gateway_prefers_latest_live_child_thread_over_active_main(
    monkeypatch: pytest.MonkeyPatch,
    threads,
    pool,
    chat_id,
    unread_count,
    expected_thread_id,
) -> None:
    started, _, enqueued = await _run_chat_delivery(
        monkeypatch,
        threads=threads,
        pool=pool,
        chat_id=chat_id,
        unread_count=unread_count,
    )

    assert started == [(expected_thread_id, chat_id, "agent-user-1")]
    assert enqueued == [(f"Human|{chat_id}|{unread_count}|ping", expected_thread_id, "human-user-1", "Human")]
