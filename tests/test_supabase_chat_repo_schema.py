from __future__ import annotations

import json

import pytest

from storage.contracts import ChatMessageRow, ChatRow
from storage.providers.supabase.chat_repo import SupabaseChatEntityRepo, SupabaseChatMessageRepo, SupabaseChatRepo
from tests.fakes.supabase import FakeSupabaseClient, FakeSupabaseResponse


class FakeRpc:
    def __init__(self, value: int):
        self._value = value

    def execute(self) -> FakeSupabaseResponse:
        return FakeSupabaseResponse([{"value": self._value}])


class ChatFakeSupabaseClient(FakeSupabaseClient):
    def __init__(self, tables: dict[str, list[dict]] | None = None):
        super().__init__(tables=tables)
        self.rpc_calls: list[tuple[str, dict]] = []

    def rpc(self, name: str, params: dict):
        self.rpc_calls.append((name, dict(params)))
        chat_id = params["p_chat_id"]
        messages = self._tables.setdefault("messages", [])
        next_seq = 1 + max((int(row.get("seq", 0)) for row in messages if row.get("chat_id") == chat_id), default=0)
        return FakeRpc(next_seq)


def test_chat_repo_creates_staging_chat_with_type_and_creator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    tables: dict[str, list[dict]] = {}
    repo = SupabaseChatRepo(ChatFakeSupabaseClient(tables))

    repo.create(
        ChatRow(
            id="chat_1",
            title="direct",
            type="direct",
            created_by_user_id="owner_1",
            created_at=1.0,
        )
    )

    assert tables["chats"] == [
        {
            "id": "chat_1",
            "type": "direct",
            "title": "direct",
            "status": "active",
            "created_by_user_id": "owner_1",
            "created_at": 1.0,
            "updated_at": None,
        }
    ]


def test_chat_member_repo_uses_staging_chat_members(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    tables: dict[str, list[dict]] = {
        "messages": [
            {"chat_id": "chat_1", "seq": 7},
        ]
    }
    repo = SupabaseChatEntityRepo(ChatFakeSupabaseClient(tables))

    repo.add_participant("chat_1", "user_1", 1.0)
    repo.update_last_read("chat_1", "user_1", 9999999999.0)

    assert tables["chat_members"] == [
        {
            "chat_id": "chat_1",
            "user_id": "user_1",
            "joined_at": 1.0,
            "last_read_seq": 7,
        }
    ]
    assert repo.list_chats_for_user("user_1") == ["chat_1"]
    assert repo.is_participant_in_chat("chat_1", "user_1") is True


def test_chat_repos_keep_public_legacy_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "public")
    tables: dict[str, list[dict]] = {
        "chat_entities": [
            {
                "chat_id": "chat_1",
                "user_id": "user_1",
                "joined_at": 1.0,
            }
        ],
        "chat_messages": [
            {
                "id": "msg_1",
                "chat_id": "chat_1",
                "sender_id": "agent_1",
                "content": "hello",
                "mentions": json.dumps(["user_1"]),
                "created_at": 2.0,
            }
        ],
    }
    client = ChatFakeSupabaseClient(tables)

    assert SupabaseChatEntityRepo(client).list_chats_for_user("user_1") == ["chat_1"]
    assert [message.id for message in SupabaseChatMessageRepo(client).list_by_chat("chat_1")] == ["msg_1"]


def test_chat_message_repo_uses_staging_messages_and_seq_rpc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    tables: dict[str, list[dict]] = {}
    client = ChatFakeSupabaseClient(tables)
    repo = SupabaseChatMessageRepo(client)

    repo.create(
        ChatMessageRow(
            id="msg_1",
            chat_id="chat_1",
            sender_id="agent_1",
            content="hello",
            mentioned_ids=["human_1"],
            created_at=2.0,
        )
    )

    assert client.rpc_calls == [("increment_chat_message_seq", {"p_chat_id": "chat_1"})]
    assert tables["messages"] == [
        {
            "id": "msg_1",
            "chat_id": "chat_1",
            "seq": 1,
            "sender_user_id": "agent_1",
            "content": "hello",
            "mentions_json": ["human_1"],
            "created_at": 2.0,
        }
    ]

    messages = repo.list_by_chat("chat_1")
    assert [(message.sender_id, message.mentioned_ids) for message in messages] == [("agent_1", ["human_1"])]


def test_chat_message_repo_counts_unread_by_last_read_seq(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    repo = SupabaseChatMessageRepo(
        ChatFakeSupabaseClient(
            {
                "chat_members": [
                    {
                        "chat_id": "chat_1",
                        "user_id": "human_1",
                        "last_read_seq": 1,
                    }
                ],
                "messages": [
                    {
                        "id": "msg_1",
                        "chat_id": "chat_1",
                        "seq": 1,
                        "sender_user_id": "agent_1",
                        "content": "old",
                        "mentions_json": json.dumps(["human_1"]),
                        "created_at": 1.0,
                    },
                    {
                        "id": "msg_2",
                        "chat_id": "chat_1",
                        "seq": 2,
                        "sender_user_id": "agent_1",
                        "content": "new mention",
                        "mentions_json": json.dumps(["human_1"]),
                        "created_at": 2.0,
                    },
                    {
                        "id": "msg_3",
                        "chat_id": "chat_1",
                        "seq": 3,
                        "sender_user_id": "human_1",
                        "content": "own",
                        "mentions_json": json.dumps([]),
                        "created_at": 3.0,
                    },
                ],
            }
        )
    )

    assert repo.count_unread("chat_1", "human_1") == 1
    assert [message.id for message in repo.list_unread("chat_1", "human_1")] == ["msg_2"]
    assert repo.has_unread_mention("chat_1", "human_1") is True
