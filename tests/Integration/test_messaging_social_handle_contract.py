from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from backend.web.utils.serializers import avatar_url
from core.agents.communication import delivery as delivery_module
from core.runtime.registry import ToolRegistry
from core.runtime.tool_result import ToolResultEnvelope
from messaging.delivery.actions import DeliveryAction
from messaging.delivery.resolver import HireVisitDeliveryResolver
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
        user_id="owner-user-1",
        owner_id="owner-user-1",
        user_repo=SimpleNamespace(
            list_all=lambda: [
                SimpleNamespace(id="agent-user-1", display_name="Toad", type="agent", owner_user_id="owner-user-1"),
            ],
            get_by_id=lambda member_id: (
                SimpleNamespace(id=member_id, display_name="Owner", owner_user_id=None) if member_id == "owner-user-1" else None
            ),
        ),
        thread_repo=SimpleNamespace(
            get_default_thread=lambda member_id: {"id": "thread-1", "user_id": "thread-user-1"} if member_id == "agent-user-1" else None
        ),
        relationship_repo=None,
    )

    for tool_name in ("list_chats", "read_messages", "send_message", "search_messages"):
        assert registry.get(tool_name) is not None

    for removed_name in ("chats", "chat_search", "directory", "wechat_send", "wechat_contacts"):
        assert registry.get(removed_name) is None


def test_send_message_schema_marks_user_id_name_as_legacy() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        user_id="agent-user-1",
        owner_id="owner-user-1",
    )

    send_message = registry.get("send_message")
    assert send_message is not None

    send_message_schema = send_message.get_schema()

    assert "legacy" in send_message_schema["parameters"]["properties"]["user_id"]["description"].lower()
    assert "directory" not in send_message_schema["description"].lower()
    assert send_message_schema["parameters"]["x-leon-required-any-of"] == [["user_id"], ["chat_id"]]


def test_read_messages_schema_requires_non_empty_chat_or_user_identifier() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        user_id="agent-user-1",
        owner_id="owner-user-1",
    )

    read_messages = registry.get("read_messages")
    assert read_messages is not None

    params = read_messages.get_schema()["parameters"]

    assert params["x-leon-required-any-of"] == [["user_id"], ["chat_id"]]
    assert params["properties"]["user_id"]["minLength"] == 1
    assert params["properties"]["chat_id"]["minLength"] == 1


def test_chat_tool_service_accepts_chat_identity_id_without_legacy_user_id() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="agent-user-1",
        owner_id="owner-user-1",
        user_repo=SimpleNamespace(
            list_all=lambda: [
                SimpleNamespace(id="agent-user-2", display_name="Morel", type="agent", owner_user_id="owner-user-1"),
            ],
            get_by_id=lambda member_id: (
                SimpleNamespace(id=member_id, display_name="Owner", owner_user_id=None) if member_id == "owner-user-1" else None
            ),
        ),
        thread_repo=SimpleNamespace(
            get_default_thread=lambda member_id: {"id": "thread-2", "user_id": "thread-user-2"} if member_id == "agent-user-2" else None
        ),
        relationship_repo=None,
    )

    assert registry.get("list_chats") is not None


def test_messaging_service_resolves_sender_name_from_thread_user_id() -> None:
    published: list[dict[str, object]] = []
    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: []),
        messages_repo=SimpleNamespace(create=lambda row: row),
        message_read_repo=SimpleNamespace(),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                None
                if uid == "thread-user-1"
                else SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None)
                if uid == "human-user-1"
                else SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None)
                if uid == "agent-user-1"
                else None
            )
        ),
        thread_repo=SimpleNamespace(
            get_by_user_id=lambda uid: {"id": "thread-1", "agent_user_id": "agent-user-1"} if uid == "thread-user-1" else None
        ),
        event_bus=SimpleNamespace(publish=lambda _chat_id, payload: published.append(payload)),
    )

    service.send("chat-1", "thread-user-1", "hello")

    payload = cast(dict[str, object], published[0])
    data = cast(dict[str, object], payload["data"])
    assert data["sender_name"] == "Toad"


def test_messaging_service_agent_send_passes_expected_read_seq_to_messages_repo() -> None:
    created_rows: list[tuple[dict[str, Any], int | None]] = []

    class _StatefulChatMemberRepo:
        def list_members(self, _chat_id: str) -> list[dict[str, Any]]:
            return []

        def last_read_seq(self, chat_id: str, user_id: str) -> int:
            assert chat_id == "chat-1"
            assert user_id == "thread-user-1"
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

    service.send("chat-1", "thread-user-1", "hello", enforce_caught_up=True)

    assert len(created_rows) == 1
    row, expected_read_seq = created_rows[0]
    assert row["sender_user_id"] == "thread-user-1"
    assert expected_read_seq == 7


def test_messaging_service_list_chats_exposes_thread_user_participant_id() -> None:
    service = MessagingService(
        chat_repo=SimpleNamespace(
            get_by_id=lambda chat_id: SimpleNamespace(id=chat_id, title=None, status="active", created_at="2026-04-07T00:00:00Z")
        ),
        chat_member_repo=SimpleNamespace(
            list_chats_for_user=lambda _user_id: ["chat-1"],
            list_members=lambda _chat_id: [{"user_id": "human-user-1"}, {"user_id": "thread-user-1"}],
        ),
        messages_repo=SimpleNamespace(list_by_chat=lambda _chat_id, limit=1: [], count_unread=lambda _chat_id, _user_id: 0),
        message_read_repo=SimpleNamespace(),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None)
                if uid == "human-user-1"
                else None
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

    chats = service.list_chats_for_user("human-user-1")

    assert chats[0]["entities"] == [
        {
            "id": "human-user-1",
            "name": "Human",
            "type": "human",
            "avatar_url": avatar_url("human-user-1", False),
        },
        {
            "id": "thread-user-1",
            "name": "Toad",
            "type": "agent",
            "avatar_url": avatar_url("agent-user-1", False),
        },
    ]


def test_messaging_service_mark_read_resets_unread_count_via_last_read_seq_watermark() -> None:
    class _StatefulChatMemberRepo:
        def __init__(self) -> None:
            self._rows = {("chat-1", "human-user-1"): {"last_read_seq": 1}}

        def list_chats_for_user(self, _user_id: str) -> list[str]:
            return ["chat-1"]

        def list_members(self, _chat_id: str) -> list[dict[str, Any]]:
            return [{"user_id": "human-user-1"}, {"user_id": "thread-user-1"}]

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
                    "sender_user_id": "thread-user-1",
                    "content": "READ_WATERMARK_OK",
                    "created_at": "2026-04-07T00:00:01Z",
                },
            ]

        def list_by_chat(self, _chat_id: str, limit: int = 50, viewer_id: str | None = None) -> list[dict[str, Any]]:
            del viewer_id
            return self._rows[-limit:]

        def count_unread(self, chat_id: str, user_id: str) -> int:
            last_read_seq = self._members_repo.last_read_seq(chat_id, user_id)
            return sum(
                1
                for row in self._rows
                if row["chat_id"] == chat_id and row["sender_user_id"] != user_id and int(row["seq"]) > last_read_seq
            )

    members_repo = _StatefulChatMemberRepo()
    messages_repo = _StatefulMessagesRepo(members_repo)
    service = MessagingService(
        chat_repo=SimpleNamespace(
            get_by_id=lambda chat_id: SimpleNamespace(id=chat_id, title=None, status="active", created_at="2026-04-07T00:00:00Z")
        ),
        chat_member_repo=members_repo,
        messages_repo=messages_repo,
        message_read_repo=SimpleNamespace(),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None)
                if uid == "human-user-1"
                else None
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

    before = service.list_chats_for_user("human-user-1")

    assert before[0]["unread_count"] == 1

    service.mark_read("chat-1", "human-user-1")

    after = service.list_chats_for_user("human-user-1")

    assert after[0]["unread_count"] == 0


def test_chat_tool_formats_thread_user_id_sender_as_agent_name() -> None:
    registry = ToolRegistry()
    service = ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        owner_id="owner-user-1",
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                None
                if uid == "thread-user-1"
                else SimpleNamespace(id=uid, display_name="Toad", owner_user_id="owner-user-1")
                if uid == "agent-user-1"
                else None
            ),
        ),
        thread_repo=SimpleNamespace(
            get_by_user_id=lambda uid: {"id": "thread-1", "agent_user_id": "agent-user-1"} if uid == "thread-user-1" else None
        ),
    )

    rendered = service._format_msgs([{"sender_id": "thread-user-1", "content": "hello"}], "human-user-1")

    assert "[Toad]: hello" in rendered


def test_chat_tool_send_accepts_thread_user_target_id() -> None:
    registry = ToolRegistry()
    sent: list[tuple[str, str, str]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        owner_id="owner-user-1",
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                None
                if uid == "thread-user-1"
                else SimpleNamespace(id=uid, display_name="Toad", owner_user_id="owner-user-1")
                if uid == "agent-user-1"
                else None
            ),
        ),
        thread_repo=SimpleNamespace(
            get_by_user_id=lambda uid: {"id": "thread-1", "agent_user_id": "agent-user-1"} if uid == "thread-user-1" else None
        ),
        chat_member_repo=SimpleNamespace(is_member=lambda _chat_id, _user_id: True),
        messaging_service=SimpleNamespace(
            find_or_create_chat=lambda user_ids: {"id": "chat-1", "user_ids": user_ids},
            count_unread=lambda _chat_id, _user_id: 0,
            send=lambda chat_id, sender_id, content, **_kwargs: sent.append((chat_id, sender_id, content)),
        ),
    )

    send_message = registry.get("send_message")
    assert send_message is not None

    result = send_message.handler(content="hello", user_id="thread-user-1")

    assert result == "Message sent to Toad."
    assert sent == [("chat-1", "human-user-1", "hello")]


def test_chat_tool_send_appends_yield_signal_to_content_and_payload() -> None:
    registry = ToolRegistry()
    sent: list[dict[str, object]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        owner_id="owner-user-1",
        chat_member_repo=SimpleNamespace(is_member=lambda _chat_id, _user_id: True),
        messaging_service=SimpleNamespace(
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


def test_chat_tool_send_requires_group_reply_to_consume_peer_unread() -> None:
    registry = ToolRegistry()
    sent: list[dict[str, object]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="thread-user-1",
        owner_id="owner-user-1",
        chat_member_repo=SimpleNamespace(is_member=lambda _chat_id, _user_id: True),
        messaging_service=SimpleNamespace(
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
        chat_identity_id="thread-user-1",
        owner_id="owner-user-1",
        chat_member_repo=SimpleNamespace(is_member=lambda _chat_id, _user_id: True),
        messaging_service=SimpleNamespace(
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


def test_read_messages_uses_thread_user_target_name_on_no_history() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        owner_id="owner-user-1",
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                None
                if uid == "thread-user-1"
                else SimpleNamespace(id=uid, display_name="Toad", owner_user_id="owner-user-1")
                if uid == "agent-user-1"
                else None
            ),
        ),
        thread_repo=SimpleNamespace(
            get_by_user_id=lambda uid: {"id": "thread-1", "agent_user_id": "agent-user-1"} if uid == "thread-user-1" else None
        ),
        chat_member_repo=SimpleNamespace(find_chat_between=lambda _eid, _user_id: None),
        messaging_service=SimpleNamespace(),
    )

    read_messages = registry.get("read_messages")
    assert read_messages is not None

    result = read_messages.handler(user_id="thread-user-1")

    assert result == "No chat history with Toad."


def test_chat_tool_search_does_not_fall_back_to_global_search_for_thread_user_target() -> None:
    registry = ToolRegistry()
    search_calls: list[tuple[str, str | None]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        owner_id="owner-user-1",
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                None
                if uid == "thread-user-1"
                else SimpleNamespace(id=uid, display_name="Toad", owner_user_id="owner-user-1")
                if uid == "agent-user-1"
                else None
            ),
        ),
        thread_repo=SimpleNamespace(
            get_by_user_id=lambda uid: {"id": "thread-1", "agent_user_id": "agent-user-1"} if uid == "thread-user-1" else None
        ),
        chat_member_repo=SimpleNamespace(find_chat_between=lambda _eid, _user_id: None),
        messaging_service=SimpleNamespace(
            search_messages=lambda query, *, chat_id=None: search_calls.append((query, chat_id)) or [{"content": "wrong"}]
        ),
    )

    search_messages = registry.get("search_messages")
    assert search_messages is not None

    result = search_messages.handler(query="hello", user_id="thread-user-1")

    assert result == "No messages matching 'hello' with Toad."
    assert search_calls == []


def test_deliver_to_agents_routes_delivery_by_thread_user_id() -> None:
    delivered: list[tuple[str, str]] = []
    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: [{"user_id": "thread-user-1"}]),
        messages_repo=SimpleNamespace(),
        message_read_repo=SimpleNamespace(),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                None
                if uid == "thread-user-1"
                else SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None)
                if uid == "agent-user-1"
                else SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None)
            )
        ),
        thread_repo=SimpleNamespace(
            get_by_user_id=lambda uid: {"id": "thread-1", "agent_user_id": "agent-user-1"} if uid == "thread-user-1" else None
        ),
        delivery_fn=lambda recipient_id, member, *_args, **_kwargs: delivered.append((recipient_id, member.id)),
    )

    service._deliver_to_agents("chat-1", "human-user-1", "hello", [])

    assert delivered == [("thread-user-1", "agent-user-1")]


def test_same_owner_group_chat_kickoff_delivers_without_relationship() -> None:
    delivered: list[tuple[str, str]] = []
    resolver = HireVisitDeliveryResolver(
        contact_repo=SimpleNamespace(get=lambda _owner_id, _target_id: None),
        chat_member_repo=SimpleNamespace(
            list_members=lambda _chat_id: [
                {"user_id": "human-user-1"},
                {"user_id": "thread-user-1"},
                {"user_id": "thread-user-2"},
            ]
        ),
        relationship_repo=SimpleNamespace(get=lambda _a, _b: None),
    )
    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(
            list_members=lambda _chat_id: [
                {"user_id": "human-user-1"},
                {"user_id": "thread-user-1"},
                {"user_id": "thread-user-2"},
            ]
        ),
        messages_repo=SimpleNamespace(),
        message_read_repo=SimpleNamespace(),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None, owner_user_id=None)
                if uid == "human-user-1"
                else None
                if uid in {"thread-user-1", "thread-user-2"}
                else SimpleNamespace(id=uid, display_name="Morel", type="agent", avatar=None, owner_user_id="human-user-1")
                if uid == "agent-user-1"
                else SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None, owner_user_id="human-user-1")
                if uid == "agent-user-2"
                else None
            )
        ),
        thread_repo=SimpleNamespace(
            get_by_user_id=lambda uid: (
                {"id": "thread-1", "agent_user_id": "agent-user-1"}
                if uid == "thread-user-1"
                else {"id": "thread-2", "agent_user_id": "agent-user-2"}
                if uid == "thread-user-2"
                else None
            )
        ),
        delivery_resolver=resolver,
        delivery_fn=lambda recipient_id, member, *_args, **_kwargs: delivered.append((recipient_id, member.id)),
    )

    service._deliver_to_agents("chat-1", "human-user-1", "hello", [])

    assert delivered == [("thread-user-1", "agent-user-1"), ("thread-user-2", "agent-user-2")]


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
                {"user_id": "thread-user-1"},
                {"user_id": "thread-user-2"},
            ]
        ),
        relationship_repo=SimpleNamespace(get=lambda _a, _b: None),
    )
    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(
            list_members=lambda _chat_id: [
                {"user_id": "human-user-1"},
                {"user_id": "thread-user-1"},
                {"user_id": "thread-user-2"},
            ]
        ),
        messages_repo=SimpleNamespace(),
        message_read_repo=SimpleNamespace(),
        user_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Human", type="human", avatar=None, owner_user_id=None)
                if uid == "human-user-1"
                else None
                if uid in {"thread-user-1", "thread-user-2"}
                else SimpleNamespace(id=uid, display_name="Morel", type="agent", avatar=None, owner_user_id="human-user-1")
                if uid == "agent-user-1"
                else SimpleNamespace(id=uid, display_name="Toad", type="agent", avatar=None, owner_user_id="human-user-1")
                if uid == "agent-user-2"
                else None
            )
        ),
        thread_repo=SimpleNamespace(
            get_by_user_id=lambda uid: (
                {"id": "thread-1", "agent_user_id": "agent-user-1"}
                if uid == "thread-user-1"
                else {"id": "thread-2", "agent_user_id": "agent-user-2"}
                if uid == "thread-user-2"
                else None
            )
        ),
        delivery_resolver=resolver,
        delivery_fn=lambda recipient_id, member, *_args, **_kwargs: delivered.append((recipient_id, member.id)),
    )

    service._deliver_to_agents("chat-1", "thread-user-1", "hello", [])

    assert delivered == [("thread-user-2", "agent-user-2")]


@pytest.mark.asyncio
async def test_async_deliver_uses_recipient_social_user_id_for_thread_lookup_and_unread(monkeypatch: pytest.MonkeyPatch) -> None:
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

    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(
                get_by_user_id=lambda uid: {"id": "thread-1", "agent_user_id": "agent-user-1"} if uid == "thread-user-1" else None
            ),
            typing_tracker=SimpleNamespace(start_chat=lambda thread_id, chat_id, user_id: started.append((thread_id, chat_id, user_id))),
            messaging_service=SimpleNamespace(count_unread=lambda chat_id, user_id: unread_calls.append((chat_id, user_id)) or 7),
            queue_manager=SimpleNamespace(
                enqueue=lambda content, thread_id, notification_type, **meta: enqueued.append(
                    (content, thread_id, meta.get("sender_id"), meta.get("sender_name"))
                )
            ),
        )
    )

    await delivery_module._async_deliver(
        app,
        "thread-user-1",
        cast(Any, SimpleNamespace(id="agent-user-1", display_name="Toad", type="agent", avatar=None)),
        "Human",
        "chat-1",
        "human-user-1",
        signal="ping",
    )

    assert started == [("thread-1", "chat-1", "thread-user-1")]
    assert unread_calls == [("chat-1", "thread-user-1")]
    assert enqueued == [("Human|chat-1|7|ping", "thread-1", "human-user-1", "Human")]
