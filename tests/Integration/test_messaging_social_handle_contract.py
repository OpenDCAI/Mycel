from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from backend.web.utils.serializers import avatar_url
from core.agents.communication import delivery as delivery_module
from core.runtime.registry import ToolRegistry
from messaging.relationships.service import RelationshipService
from messaging.service import MessagingService
from messaging.tools.chat_tool_service import ChatToolService


class _FakeRelationshipRepo:
    def __init__(self) -> None:
        self._existing = {
            ("agent-user-1", "human-user-1"): {
                "id": "rel-1",
                "principal_a": "agent-user-1",
                "principal_b": "human-user-1",
                "state": "hire",
                "direction": "b_to_a",
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
        member_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, name="Toad", type="mycel_agent", avatar=None)
                if uid == "agent-user-1"
                else SimpleNamespace(id=uid, name="Human", type="human", avatar=None)
            )
        ),
        delivery_fn=lambda recipient_id, member, *_args, **_kwargs: delivered.append((recipient_id, member.id)),
    )

    service._deliver_to_agents("chat-1", "human-user-1", "hello", [])

    assert delivered == [("agent-user-1", "agent-user-1")]


def test_relationship_hire_snapshot_drops_main_thread_id():
    repo = _FakeRelationshipRepo()
    service = RelationshipService(
        relationship_repo=repo,
        member_repo=SimpleNamespace(
            get_by_id=lambda user_id: SimpleNamespace(id=user_id, name="Toad") if user_id == "agent-user-1" else None
        ),
    )

    row = service.revoke("human-user-1", "agent-user-1")

    assert row.hire_snapshot is not None
    assert row.hire_snapshot["user_id"] == "agent-user-1"
    assert row.hire_snapshot["name"] == "Toad"
    assert "main_thread_id" not in row.hire_snapshot


def test_relationship_hire_snapshot_resolves_thread_user_name_via_member() -> None:
    repo = _FakeRelationshipRepo()
    repo._existing[("human-user-1", "thread-user-1")] = {
        "id": "rel-2",
        "principal_a": "human-user-1",
        "principal_b": "thread-user-1",
        "state": "hire",
        "direction": "b_to_a",
        "created_at": "2026-04-07T00:00:00Z",
        "updated_at": "2026-04-07T00:00:00Z",
    }
    service = RelationshipService(
        relationship_repo=repo,
        member_repo=SimpleNamespace(
            get_by_id=lambda user_id: (
                None if user_id == "thread-user-1" else SimpleNamespace(id=user_id, name="Toad") if user_id == "member-agent-1" else None
            )
        ),
        thread_repo=SimpleNamespace(
            get_by_user_id=lambda user_id: {"id": "thread-1", "member_id": "member-agent-1"} if user_id == "thread-user-1" else None
        ),
    )

    row = service.revoke("human-user-1", "thread-user-1")

    assert row.hire_snapshot is not None
    assert row.hire_snapshot["user_id"] == "thread-user-1"
    assert row.hire_snapshot["name"] == "Toad"


def test_chat_tool_directory_uses_neutral_id_label() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        user_id="owner-user-1",
        owner_id="owner-user-1",
        member_repo=SimpleNamespace(
            list_all=lambda: [
                SimpleNamespace(id="agent-user-1", name="Toad", type="mycel_agent", owner_user_id="owner-user-1"),
            ],
            get_by_id=lambda member_id: (
                SimpleNamespace(id=member_id, name="Owner", owner_user_id=None) if member_id == "owner-user-1" else None
            ),
        ),
        relationship_repo=None,
    )

    directory = registry.get("directory")
    assert directory is not None

    result = directory.handler()
    assert isinstance(result, str)

    assert "id=agent-user-1" in result
    assert "user_id=agent-user-1" not in result


def test_chat_tool_send_schema_marks_user_id_name_as_legacy() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        user_id="agent-user-1",
        owner_id="owner-user-1",
    )

    chat_send = registry.get("chat_send")
    directory = registry.get("directory")
    assert chat_send is not None
    assert directory is not None

    chat_send_schema = chat_send.get_schema()
    directory_schema = directory.get_schema()

    assert "legacy" in chat_send_schema["parameters"]["properties"]["user_id"]["description"].lower()
    assert "chat_send(user_id" in directory_schema["description"]


def test_chat_tool_service_accepts_chat_identity_id_without_legacy_user_id() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="agent-user-1",
        owner_id="owner-user-1",
        member_repo=SimpleNamespace(
            list_all=lambda: [
                SimpleNamespace(id="agent-user-2", name="Morel", type="mycel_agent", owner_user_id="owner-user-1"),
            ],
            get_by_id=lambda member_id: (
                SimpleNamespace(id=member_id, name="Owner", owner_user_id=None) if member_id == "owner-user-1" else None
            ),
        ),
        relationship_repo=None,
    )

    directory = registry.get("directory")
    assert directory is not None
    result = directory.handler()
    assert isinstance(result, str)
    assert "id=agent-user-2" in result


def test_messaging_service_resolves_sender_name_from_thread_user_id() -> None:
    published: list[dict[str, object]] = []
    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: []),
        messages_repo=SimpleNamespace(create=lambda row: row),
        message_read_repo=SimpleNamespace(),
        member_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                None
                if uid == "thread-user-1"
                else SimpleNamespace(id=uid, name="Human", type="human", avatar=None)
                if uid == "human-user-1"
                else SimpleNamespace(id=uid, name="Toad", type="mycel_agent", avatar=None)
                if uid == "member-agent-1"
                else None
            )
        ),
        thread_repo=SimpleNamespace(
            get_by_user_id=lambda uid: {"id": "thread-1", "member_id": "member-agent-1"} if uid == "thread-user-1" else None
        ),
        event_bus=SimpleNamespace(publish=lambda _chat_id, payload: published.append(payload)),
    )

    service.send("chat-1", "thread-user-1", "hello")

    payload = cast(dict[str, object], published[0])
    data = cast(dict[str, object], payload["data"])
    assert data["sender_name"] == "Toad"


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
        member_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, name="Human", type="human", avatar=None)
                if uid == "human-user-1"
                else None
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
            "type": "mycel_agent",
            "avatar_url": avatar_url("member-agent-1", False),
        },
    ]


def test_chat_tool_formats_thread_user_id_sender_as_agent_name() -> None:
    registry = ToolRegistry()
    service = ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        owner_id="owner-user-1",
        member_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                None
                if uid == "thread-user-1"
                else SimpleNamespace(id=uid, name="Toad", owner_user_id="owner-user-1")
                if uid == "member-agent-1"
                else None
            ),
        ),
        thread_repo=SimpleNamespace(
            get_by_user_id=lambda uid: {"id": "thread-1", "member_id": "member-agent-1"} if uid == "thread-user-1" else None
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
        member_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                None
                if uid == "thread-user-1"
                else SimpleNamespace(id=uid, name="Toad", owner_user_id="owner-user-1")
                if uid == "member-agent-1"
                else None
            ),
        ),
        thread_repo=SimpleNamespace(
            get_by_user_id=lambda uid: {"id": "thread-1", "member_id": "member-agent-1"} if uid == "thread-user-1" else None
        ),
        chat_member_repo=SimpleNamespace(is_member=lambda _chat_id, _user_id: True),
        messaging_service=SimpleNamespace(
            find_or_create_chat=lambda user_ids: {"id": "chat-1", "user_ids": user_ids},
            count_unread=lambda _chat_id, _user_id: 0,
            send=lambda chat_id, sender_id, content, **_kwargs: sent.append((chat_id, sender_id, content)),
        ),
    )

    chat_send = registry.get("chat_send")
    assert chat_send is not None

    result = chat_send.handler(content="hello", user_id="thread-user-1")

    assert result == "Message sent to Toad."
    assert sent == [("chat-1", "human-user-1", "hello")]


def test_chat_tool_read_uses_thread_user_target_name_on_no_history() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        owner_id="owner-user-1",
        member_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                None
                if uid == "thread-user-1"
                else SimpleNamespace(id=uid, name="Toad", owner_user_id="owner-user-1")
                if uid == "member-agent-1"
                else None
            ),
        ),
        thread_repo=SimpleNamespace(
            get_by_user_id=lambda uid: {"id": "thread-1", "member_id": "member-agent-1"} if uid == "thread-user-1" else None
        ),
        chat_member_repo=SimpleNamespace(find_chat_between=lambda _eid, _user_id: None),
        messaging_service=SimpleNamespace(),
    )

    chat_read = registry.get("chat_read")
    assert chat_read is not None

    result = chat_read.handler(user_id="thread-user-1")

    assert result == "No chat history with Toad."


def test_chat_tool_search_does_not_fall_back_to_global_search_for_thread_user_target() -> None:
    registry = ToolRegistry()
    search_calls: list[tuple[str, str | None]] = []
    ChatToolService(
        registry=registry,
        chat_identity_id="human-user-1",
        owner_id="owner-user-1",
        member_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                None
                if uid == "thread-user-1"
                else SimpleNamespace(id=uid, name="Toad", owner_user_id="owner-user-1")
                if uid == "member-agent-1"
                else None
            ),
        ),
        thread_repo=SimpleNamespace(
            get_by_user_id=lambda uid: {"id": "thread-1", "member_id": "member-agent-1"} if uid == "thread-user-1" else None
        ),
        chat_member_repo=SimpleNamespace(find_chat_between=lambda _eid, _user_id: None),
        messaging_service=SimpleNamespace(
            search_messages=lambda query, *, chat_id=None: search_calls.append((query, chat_id)) or [{"content": "wrong"}]
        ),
    )

    chat_search = registry.get("chat_search")
    assert chat_search is not None

    result = chat_search.handler(query="hello", user_id="thread-user-1")

    assert result == "No messages matching 'hello' with Toad."
    assert search_calls == []


def test_deliver_to_agents_routes_delivery_by_thread_user_id() -> None:
    delivered: list[tuple[str, str]] = []
    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(list_members=lambda _chat_id: [{"user_id": "thread-user-1"}]),
        messages_repo=SimpleNamespace(),
        message_read_repo=SimpleNamespace(),
        member_repo=SimpleNamespace(
            get_by_id=lambda uid: (
                None
                if uid == "thread-user-1"
                else SimpleNamespace(id=uid, name="Toad", type="mycel_agent", avatar=None)
                if uid == "member-agent-1"
                else SimpleNamespace(id=uid, name="Human", type="human", avatar=None)
            )
        ),
        thread_repo=SimpleNamespace(
            get_by_user_id=lambda uid: {"id": "thread-1", "member_id": "member-agent-1"} if uid == "thread-user-1" else None
        ),
        delivery_fn=lambda recipient_id, member, *_args, **_kwargs: delivered.append((recipient_id, member.id)),
    )

    service._deliver_to_agents("chat-1", "human-user-1", "hello", [])

    assert delivered == [("thread-user-1", "member-agent-1")]


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
                get_by_user_id=lambda uid: {"id": "thread-1", "member_id": "member-agent-1"} if uid == "thread-user-1" else None
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
        cast(Any, SimpleNamespace(id="member-agent-1", name="Toad", type="mycel_agent", avatar=None)),
        "Human",
        "chat-1",
        "human-user-1",
        signal="ping",
    )

    assert started == [("thread-1", "chat-1", "thread-user-1")]
    assert unread_calls == [("chat-1", "thread-user-1")]
    assert enqueued == [("Human|chat-1|7|ping", "thread-1", "human-user-1", "Human")]
