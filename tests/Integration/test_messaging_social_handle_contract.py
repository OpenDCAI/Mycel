from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any, cast

import pytest

from backend.web.utils.serializers import avatar_url
from core.agents.communication import delivery as delivery_module
from core.runtime.middleware.monitor import AgentState
from core.runtime.registry import ToolRegistry
from core.runtime.tool_result import ToolResultEnvelope
from messaging.delivery.actions import DeliveryAction
from messaging.delivery.resolver import HireVisitDeliveryResolver
from messaging.display_user import resolve_messaging_display_user
from messaging.relationships.service import RelationshipService
from messaging.service import MessagingService
from messaging.tools.chat_tool_service import ChatToolService


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

    def get(self, actor_id: str, target_id: str):
        key = cast(tuple[str, str], tuple(sorted((actor_id, target_id))))
        return self._existing.get(key)

    def upsert(self, actor_id: str, target_id: str, **fields):
        key = cast(tuple[str, str], tuple(sorted((actor_id, target_id))))
        row = dict(self._existing[key])
        row.update(fields)
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


def test_messaging_display_user_resolver_does_not_bridge_removed_thread_user_id() -> None:
    resolved = resolve_messaging_display_user(
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                None
                if uid == "thread-user-1"
                else SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None)
                if uid == "agent-user-1"
                else None
            )
        ),
        social_user_id="thread-user-1",
    )

    assert resolved is None


def test_deliver_to_agents_does_not_require_main_thread_id():
    delivered: list[tuple[str, str]] = []
    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: [{"user_id": "agent-user-1"}]),
        messages_repo=SimpleNamespace(),
        message_read_repo=SimpleNamespace(),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None)
                if uid == "agent-user-1"
                else SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None)
            )
        ),
        delivery_fn=lambda recipient_id, member, *_args, **_kwargs: delivered.append((recipient_id, member.id)),
    )

    service._deliver_to_agents("chat-1", "human-user-1", "hello", [])

    assert delivered == [("agent-user-1", "agent-user-1")]


def test_relationship_revoke_deletes_hire_without_snapshot_side_channel() -> None:
    repo = _FakeRelationshipRepo()
    service = RelationshipService(repo)

    row = service.revoke("human-user-1", "agent-user-1")

    assert row.state == "none"
    assert "hire_snapshot" not in repo._existing[("agent-user-1", "human-user-1")]


def test_relationship_request_uses_single_pending_state_and_initiator() -> None:
    class _RequestRepo:
        def get(self, _actor_id: str, _target_id: str):
            return None

        def upsert(self, _actor_id: str, _target_id: str, **fields: Any):
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


def test_relationship_upgrade_does_not_write_removed_hire_timestamp_columns() -> None:
    captured: dict[str, Any] = {}

    class _UpgradeRepo:
        def get(self, _actor_id: str, _target_id: str):
            return {
                "id": "hire_visit:agent-user-1:human-user-1",
                "user_low": "agent-user-1",
                "user_high": "human-user-1",
                "kind": "hire_visit",
                "state": "visit",
                "initiator_user_id": "human-user-1",
                "created_at": "2026-04-07T00:00:00Z",
                "updated_at": "2026-04-07T00:00:01Z",
            }

        def upsert(self, _actor_id: str, _target_id: str, **fields: Any):
            captured.update(fields)
            return {
                "id": "hire_visit:agent-user-1:human-user-1",
                "user_low": "agent-user-1",
                "user_high": "human-user-1",
                "kind": "hire_visit",
                "created_at": "2026-04-07T00:00:00Z",
                "updated_at": "2026-04-07T00:00:02Z",
                **fields,
            }

    service = RelationshipService(_UpgradeRepo())

    row = service.upgrade("human-user-1", "agent-user-1")

    assert row.state == "hire"
    assert "hire_granted_at" not in captured
    assert "hire_revoked_at" not in captured
    assert "hire_snapshot" not in captured


def test_chat_tool_registry_exposes_final_contract_only() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="owner-user-1",
        messaging_service=_messaging_display_service(),
    )

    for tool_name in ("list_chats", "read_messages", "send_message", "search_messages"):
        assert registry.get(tool_name) is not None

    for removed_name in ("chats", "chat_search", "directory", "wechat_send", "wechat_contacts"):
        assert registry.get(removed_name) is None


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
    assert "legacy" not in send_message_schema["description"].lower()
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


def test_chat_tool_service_rejects_removed_constructor_user_id() -> None:
    registry = ToolRegistry()

    with pytest.raises(TypeError, match="user_id"):
        ChatToolService(
            registry=registry,
            user_id="agent-user-1",
            messaging_service=_messaging_display_service(),
        )


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
        message_read_repo=SimpleNamespace(),
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
        message_read_repo=SimpleNamespace(),
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
        message_read_repo=SimpleNamespace(),
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
        message_read_repo=SimpleNamespace(),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None) if uid == "agent-user-1" else None
        ),
    )

    service.send("chat-1", "agent-user-1", "hello", enforce_caught_up=True)

    assert len(created_rows) == 1
    row, expected_read_seq = created_rows[0]
    assert row["sender_user_id"] == "agent-user-1"
    assert expected_read_seq == 7


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
        message_read_repo=SimpleNamespace(),
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


def test_messaging_service_list_chats_ignores_blank_other_names_in_title_fallback() -> None:
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
        message_read_repo=SimpleNamespace(),
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
                    {"chat_id": "chat-1", "user_id": "human-user-1", "last_read_seq": 4},
                    {"chat_id": "chat-1", "user_id": "agent-user-1", "last_read_seq": 0},
                    {"chat_id": "chat-closed", "user_id": "human-user-1", "last_read_seq": 0},
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
        message_read_repo=SimpleNamespace(),
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
        message_read_repo=SimpleNamespace(),
        user_repo=SimpleNamespace(
            list_by_ids=lambda _user_ids: [SimpleNamespace(id="human-user-1", display_name="Human", type="human", avatar=None)],
        ),
    )

    with pytest.raises(RuntimeError, match="Chat member missing-user is not a resolvable user row"):
        service.list_conversation_summaries_for_user("human-user-1")


def test_messaging_service_conversation_summaries_loads_users_and_unread_counts_in_parallel() -> None:
    users_started = threading.Event()
    unread_started = threading.Event()

    def _list_users(user_ids: list[str]):
        users_started.set()
        if not unread_started.wait(0.2):
            raise AssertionError("unread counts did not start while users were loading")
        return [
            SimpleNamespace(id=user_id, display_name=user_id, type="human", avatar=None)
            for user_id in user_ids
        ]

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
        message_read_repo=SimpleNamespace(),
        user_repo=SimpleNamespace(list_by_ids=_list_users),
    )

    summaries = service.list_conversation_summaries_for_user("human-user-1")

    assert summaries[0]["unread_count"] == 2


def test_messaging_service_get_chat_detail_exposes_agent_user_participant_id() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(
            list_members=lambda _chat_id: [{"user_id": "human-user-1"}, {"user_id": "agent-user-1"}],
        ),
        messages_repo=SimpleNamespace(),
        message_read_repo=SimpleNamespace(),
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
            created_at="2026-04-07T00:00:00Z",
        )
    )

    assert detail == {
        "id": "chat-1",
        "title": "Chat title",
        "status": "active",
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
        message_read_repo=SimpleNamespace(),
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


def test_chat_tool_search_does_not_fall_back_to_global_search_for_agent_user_target() -> None:
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


def test_deliver_to_agents_routes_delivery_by_agent_user_id() -> None:
    delivered: list[tuple[str, str]] = []
    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: [{"user_id": "agent-user-1"}]),
        messages_repo=SimpleNamespace(),
        message_read_repo=SimpleNamespace(),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None)
                if uid == "agent-user-1"
                else SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None)
            )
        ),
        delivery_fn=lambda recipient_id, member, *_args, **_kwargs: delivered.append((recipient_id, member.id)),
    )

    service._deliver_to_agents("chat-1", "human-user-1", "hello", [])

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
    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(
            list_members=lambda _chat_id: [
                {"user_id": "human-user-1"},
                {"user_id": "agent-user-1"},
                {"user_id": "agent-user-2"},
            ]
        ),
        messages_repo=SimpleNamespace(),
        message_read_repo=SimpleNamespace(),
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
        delivery_resolver=resolver,
        delivery_fn=lambda recipient_id, member, *_args, **_kwargs: delivered.append((recipient_id, member.id)),
    )

    service._deliver_to_agents("chat-1", "human-user-1", "hello", [])

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


def test_delivery_resolver_requires_current_chat_member_contract() -> None:
    resolver = HireVisitDeliveryResolver(
        contact_repo=SimpleNamespace(get=lambda _owner_id, _target_id: None),
        chat_member_repo=SimpleNamespace(),
        relationship_repo=None,
    )

    with pytest.raises(AttributeError):
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


def test_same_owner_agent_turn_delivers_to_sibling_actor_without_relationship() -> None:
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
    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(
            list_members=lambda _chat_id: [
                {"user_id": "human-user-1"},
                {"user_id": "agent-user-1"},
                {"user_id": "agent-user-2"},
            ]
        ),
        messages_repo=SimpleNamespace(),
        message_read_repo=SimpleNamespace(),
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
        delivery_resolver=resolver,
        delivery_fn=lambda recipient_id, member, *_args, **_kwargs: delivered.append((recipient_id, member.id)),
    )

    service._deliver_to_agents("chat-1", "agent-user-1", "hello", [])

    assert delivered == [("agent-user-2", "agent-user-2")]


@pytest.mark.asyncio
async def test_async_deliver_uses_recipient_social_user_id_for_thread_lookup_and_unread(monkeypatch: pytest.MonkeyPatch) -> None:
    started, unread_calls, enqueued = await _run_chat_delivery(monkeypatch, chat_id="chat-1", unread_count=7)

    assert started == [("thread-1", "chat-1", "agent-user-1")]
    assert unread_calls == [("chat-1", "agent-user-1")]
    assert enqueued == [("Human|chat-1|7|ping", "thread-1", "human-user-1", "Human")]


def test_recipient_thread_resolution_requires_current_thread_repo_contract() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(
                get_by_user_id=lambda uid: {"id": "thread-1", "agent_user_id": "agent-user-1"} if uid == "agent-user-1" else None
            ),
            agent_pool={},
        )
    )

    with pytest.raises(AttributeError):
        delivery_module._resolve_recipient_thread_id(app, "agent-user-1")


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

    monkeypatch.setattr("backend.web.services.agent_pool.get_or_create_agent", _fake_get_or_create_agent)
    monkeypatch.setattr("backend.web.services.agent_pool.resolve_thread_sandbox", lambda _app, _thread_id: "local")
    monkeypatch.setattr("backend.web.services.streaming_service._ensure_thread_handlers", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "core.runtime.middleware.queue.formatters.format_chat_notification",
        lambda sender_name, chat_id, unread_count, signal=None: f"{sender_name}|{chat_id}|{unread_count}|{signal}",
    )

    thread_rows = threads or [{"id": "thread-1", "agent_user_id": "agent-user-1", "is_main": True, "branch_index": 0}]
    default_thread = next((row for row in thread_rows if row.get("is_main")), thread_rows[0])
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(
                get_by_user_id=lambda uid: default_thread if uid == "agent-user-1" else None,
                list_by_agent_user=lambda uid: list(thread_rows) if uid == "agent-user-1" else [],
            ),
            agent_pool=pool or {},
            typing_tracker=SimpleNamespace(start_chat=lambda thread_id, chat_id, user_id: started.append((thread_id, chat_id, user_id))),
            messaging_service=SimpleNamespace(
                count_unread=lambda chat_id, user_id: unread_calls.append((chat_id, user_id)) or unread_count
            ),
            queue_manager=SimpleNamespace(
                enqueue=lambda content, thread_id, notification_type, **meta: enqueued.append(
                    (content, thread_id, meta.get("sender_id"), meta.get("sender_name"))
                )
            ),
        )
    )

    await delivery_module._async_deliver(
        app,
        "agent-user-1",
        cast(Any, SimpleNamespace(id="agent-user-1", display_name="Toad", type="agent", avatar=None)),
        "Human",
        chat_id,
        "human-user-1",
        signal="ping",
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
async def test_async_deliver_prefers_latest_live_child_thread_over_active_main(
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
