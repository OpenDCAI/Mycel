from __future__ import annotations

import pytest

from storage.contracts import ChatRow, ContactEdgeRow
from storage.providers.supabase.chat_repo import SupabaseChatRepo
from storage.providers.supabase.contact_repo import SupabaseContactRepo
from storage.providers.supabase.messaging_repo import (
    SupabaseChatMemberRepo,
    SupabaseMessagesRepo,
    SupabaseRelationshipRepo,
)
from tests.fakes.supabase import FakeSupabaseClient


def test_supabase_chat_stack_uses_chat_schema_for_root_tables() -> None:
    tables: dict[str, list[dict]] = {
        "chat.chats": [{"id": "chat-1", "next_message_seq": 0}],
        "chat.chat_members": [{"chat_id": "chat-1", "user_id": "user-1", "last_read_seq": 0}],
        "chat.messages": [],
    }
    client = FakeSupabaseClient(tables=tables)

    SupabaseChatRepo(client).create(
        ChatRow(
            id="chat-2",
            type="direct",
            created_by_user_id="user-1",
            title=None,
            status="active",
            next_message_seq=0,
            created_at=123.0,
        )
    )
    SupabaseChatMemberRepo(client).add_member("chat-2", "user-2")
    message = SupabaseMessagesRepo(client).create(
        {
            "id": "msg-1",
            "chat_id": "chat-1",
            "sender_user_id": "user-1",
            "content": "hello",
            "created_at": 123.0,
        },
        expected_read_seq=0,
    )

    assert message["seq"] == 1
    assert any(row["id"] == "chat-2" for row in tables["chat.chats"])
    assert any(row["user_id"] == "user-2" for row in tables["chat.chat_members"])
    assert any(row["id"] == "msg-1" for row in tables["chat.messages"])
    assert "chats" not in tables
    assert "chat_members" not in tables
    assert "messages" not in tables


def test_supabase_contact_and_relationship_repos_use_chat_schema() -> None:
    tables: dict[str, list[dict]] = {"chat.contacts": [], "chat.relationships": []}
    client = FakeSupabaseClient(tables=tables)

    SupabaseContactRepo(client).upsert(
        ContactEdgeRow(
            source_user_id="user-1",
            target_user_id="user-2",
            kind="normal",
            state="active",
            muted=False,
            blocked=False,
            created_at=123.0,
        )
    )
    relationship = SupabaseRelationshipRepo(client).upsert(
        "user-1",
        "user-2",
        state="pending",
        initiator_user_id="user-1",
    )

    assert tables["chat.contacts"][0]["source_user_id"] == "user-1"
    assert relationship["id"] == "hire_visit:user-1:user-2"
    assert tables["chat.relationships"][0]["initiator_user_id"] == "user-1"
    assert "contacts" not in tables
    assert "relationships" not in tables


class _FakeResponse:
    def __init__(self, data=None, count=None) -> None:
        self.data = data
        self.count = count


class _FakeTable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.select_calls: list[object] = []
        self.eq_calls: list[tuple[str, object]] = []
        self.neq_calls: list[tuple[str, object]] = []
        self.gt_calls: list[tuple[str, object]] = []
        self.lt_calls: list[tuple[str, object]] = []
        self.is_calls: list[tuple[str, object]] = []
        self.order_calls: list[tuple[str, bool]] = []
        self.limit_calls: list[int] = []
        self.insert_payload = None
        self.update_payload = None
        self.upsert_payload = None
        self.on_conflict = None
        self.delete_count = 0
        self.rows = []
        self.count = None

    def select(self, cols, count=None):
        self.select_calls.append((cols, count))
        return self

    def eq(self, key, value):
        self.eq_calls.append((key, value))
        return self

    def neq(self, key, value):
        self.neq_calls.append((key, value))
        return self

    def gt(self, key, value):
        self.gt_calls.append((key, value))
        return self

    def lt(self, key, value):
        self.lt_calls.append((key, value))
        return self

    def is_(self, key, value):
        self.is_calls.append((key, value))
        return self

    def order(self, key, desc=False):
        self.order_calls.append((key, desc))
        return self

    def limit(self, value):
        self.limit_calls.append(value)
        return self

    def insert(self, payload):
        self.insert_payload = payload
        return self

    def upsert(self, payload, on_conflict=None):
        self.upsert_payload = payload
        self.on_conflict = on_conflict
        return self

    def update(self, payload):
        self.update_payload = payload
        return self

    def delete(self):
        self.delete_count += 1
        return self

    def execute(self):
        return _FakeResponse(data=self.rows, count=self.count)


class _FakeClient:
    def __init__(self, *, schema_name: str | None = None, root: _FakeClient | None = None) -> None:
        self._schema_name = schema_name
        self._root = root or self
        if root is None:
            self.tables: dict[str, _FakeTable] = {}
            self.table_calls: list[str] = []
            self.rpc_calls: list[tuple[str, dict[str, object]]] = []
            self.rpc_data = [{"increment_chat_message_seq": 7}]

    def table(self, name: str):
        resolved = f"{self._schema_name}.{name}" if self._schema_name else name
        self._root.table_calls.append(resolved)
        table = self._root.tables.get(resolved)
        if table is None:
            table = _FakeTable(resolved)
            self._root.tables[resolved] = table
        return table

    def schema(self, name: str):
        return _FakeClient(schema_name=name, root=self._root)

    def rpc(self, name: str, params: dict[str, object]):
        resolved = f"{self._schema_name}.{name}" if self._schema_name else name
        self._root.rpc_calls.append((resolved, params))

        class _Rpc:
            def __init__(self, data):
                self._data = data

            def execute(self):
                return _FakeResponse(data=self._data)

        return _Rpc(self._root.rpc_data)


def test_supabase_chat_repo_create_persists_chat_root_fields() -> None:
    client = _FakeClient()
    repo = SupabaseChatRepo(client)

    repo.create(
        ChatRow(
            id="chat-1",
            type="group",
            created_by_user_id="user-1",
            title="Test",
            status="active",
            next_message_seq=0,
            created_at=123.0,
        )
    )

    payload = client.tables["chat.chats"].insert_payload
    assert payload is not None
    assert payload["type"] == "group"
    assert payload["created_by_user_id"] == "user-1"
    assert payload["next_message_seq"] == 0


def test_supabase_chat_repo_get_by_id_hydrates_chat_root_fields() -> None:
    client = _FakeClient()
    client.schema("chat").table("chats").rows = [
        {
            "id": "chat-1",
            "type": "direct",
            "created_by_user_id": "user-1",
            "title": "DM",
            "status": "active",
            "next_message_seq": 4,
            "created_at": 123.0,
            "updated_at": 124.0,
        }
    ]
    repo = SupabaseChatRepo(client)

    row = repo.get_by_id("chat-1")

    assert row is not None
    assert row.type == "direct"
    assert row.created_by_user_id == "user-1"
    assert row.next_message_seq == 4


def test_supabase_chat_repo_delete_removes_child_rows_before_chat_root() -> None:
    client = _FakeClient()
    repo = SupabaseChatRepo(client)

    repo.delete("chat-1")

    assert client.table_calls == ["chat.messages", "chat.chat_members", "chat.chats"]
    assert client.tables["chat.messages"].delete_count == 1
    assert client.tables["chat.chat_members"].delete_count == 1
    assert client.tables["chat.chats"].delete_count == 1
    assert ("chat_id", "chat-1") in client.tables["chat.messages"].eq_calls
    assert ("chat_id", "chat-1") in client.tables["chat.chat_members"].eq_calls
    assert ("id", "chat-1") in client.tables["chat.chats"].eq_calls


def test_supabase_chat_member_repo_updates_last_read_seq() -> None:
    client = _FakeClient()
    repo = SupabaseChatMemberRepo(client)

    repo.update_last_read("chat-1", "user-1", 7)

    table = client.tables["chat.chat_members"]
    assert table.update_payload == {"last_read_seq": 7}
    assert ("chat_id", "chat-1") in table.eq_calls
    assert ("user_id", "user-1") in table.eq_calls


def test_supabase_chat_member_repo_add_member_persists_numeric_joined_at() -> None:
    client = _FakeClient()
    repo = SupabaseChatMemberRepo(client)

    repo.add_member("chat-1", "user-1")

    payload = client.tables["chat.chat_members"].upsert_payload
    assert payload is not None
    assert payload["chat_id"] == "chat-1"
    assert payload["user_id"] == "user-1"
    assert client.tables["chat.chat_members"].on_conflict == "chat_id,user_id"
    assert isinstance(payload["joined_at"], float)


def test_supabase_messages_repo_create_allocates_seq_and_uses_message_root_fields() -> None:
    client = _FakeClient()
    client.schema("chat").table("messages").rows = [
        {
            "id": "msg-1",
            "chat_id": "chat-1",
            "seq": 7,
            "sender_user_id": "user-1",
            "content": "hello",
            "mentions_json": ["user-2"],
            "created_at": 123.0,
        }
    ]
    repo = SupabaseMessagesRepo(client)

    row = repo.create(
        {
            "id": "msg-1",
            "chat_id": "chat-1",
            "sender_user_id": "user-1",
            "content": "hello",
            "mentions_json": ["user-2"],
            "created_at": 123.0,
        }
    )

    assert client.rpc_calls == [("chat.increment_chat_message_seq", {"p_chat_id": "chat-1"})]
    payload = client.tables["chat.messages"].insert_payload
    assert payload is not None
    assert payload["seq"] == 7
    assert payload["sender_user_id"] == "user-1"
    assert "sender_id" not in payload
    assert row["seq"] == 7


def test_supabase_messages_repo_create_accepts_scalar_rpc_seq() -> None:
    client = _FakeClient()
    client.rpc_data = 8
    client.schema("chat").table("messages").rows = [
        {
            "id": "msg-2",
            "chat_id": "chat-2",
            "seq": 8,
            "sender_user_id": "user-1",
            "content": "hello",
            "mentions_json": [],
            "created_at": 123.0,
        }
    ]
    repo = SupabaseMessagesRepo(client)

    row = repo.create(
        {
            "id": "msg-2",
            "chat_id": "chat-2",
            "sender_user_id": "user-1",
            "content": "hello",
            "mentions_json": [],
            "created_at": 123.0,
        }
    )

    payload = client.tables["chat.messages"].insert_payload
    assert payload is not None
    assert payload["seq"] == 8
    assert row["seq"] == 8


def test_supabase_messages_repo_create_with_expected_read_seq_uses_chat_cas() -> None:
    client = _FakeClient()
    client.schema("chat").table("chats").rows = [{"id": "chat-1", "next_message_seq": 6}]
    client.schema("chat").table("messages").rows = [
        {
            "id": "msg-7",
            "chat_id": "chat-1",
            "seq": 7,
            "sender_user_id": "user-1",
            "content": "hello",
            "mentions_json": [],
            "created_at": 123.0,
        }
    ]
    repo = SupabaseMessagesRepo(client)

    row = repo.create(
        {
            "id": "msg-7",
            "chat_id": "chat-1",
            "sender_user_id": "user-1",
            "content": "hello",
            "mentions_json": [],
            "created_at": 123.0,
        },
        expected_read_seq=6,
    )

    assert client.rpc_calls == []
    chats = client.tables["chat.chats"]
    assert chats.update_payload == {"next_message_seq": 7}
    assert ("id", "chat-1") in chats.eq_calls
    assert ("next_message_seq", 6) in chats.eq_calls
    payload = client.tables["chat.messages"].insert_payload
    assert payload is not None
    assert payload["seq"] == 7
    assert row["seq"] == 7


def test_supabase_messages_repo_create_with_stale_expected_read_seq_fails_loudly() -> None:
    client = _FakeClient()
    client.schema("chat").table("chats").rows = []
    repo = SupabaseMessagesRepo(client)

    with pytest.raises(RuntimeError, match="Chat advanced after your last read. Call read_messages\\(chat_id='chat-1'\\) first\\."):
        repo.create(
            {
                "id": "msg-7",
                "chat_id": "chat-1",
                "sender_user_id": "user-1",
                "content": "hello",
                "mentions_json": [],
                "created_at": 123.0,
            },
            expected_read_seq=6,
        )


def test_supabase_messages_repo_list_by_chat_uses_seq_ordering() -> None:
    client = _FakeClient()
    client.schema("chat").table("messages").rows = [{"id": "msg-6", "seq": 6}, {"id": "msg-7", "seq": 7}]
    repo = SupabaseMessagesRepo(client)

    repo.list_by_chat("chat-1", limit=20, before="7")

    table = client.tables["chat.messages"]
    assert ("seq", 7) in table.lt_calls
    assert table.order_calls == [("seq", True)]


def test_supabase_messages_repo_count_unread_uses_last_read_seq_and_sender_user_id() -> None:
    client = _FakeClient()
    client.schema("chat").table("chat_members").rows = [{"last_read_seq": 5}]
    client.schema("chat").table("messages").count = 2
    repo = SupabaseMessagesRepo(client)

    count = repo.count_unread("chat-1", "user-1")

    assert count == 2
    assert ("last_read_seq", None) in client.tables["chat.chat_members"].select_calls
    assert ("seq", 5) in client.tables["chat.messages"].gt_calls
    assert ("sender_user_id", "user-1") in client.tables["chat.messages"].neq_calls
    assert ("sender_id", "user-1") not in client.tables["chat.messages"].neq_calls
