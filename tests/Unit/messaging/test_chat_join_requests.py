from __future__ import annotations

from types import SimpleNamespace

import pytest

from messaging.join_requests import ChatJoinRequestService


class _Members:
    def __init__(self) -> None:
        self.members: set[tuple[str, str]] = {("chat-1", "owner-1")}
        self.added: list[tuple[str, str]] = []

    def is_member(self, chat_id: str, user_id: str) -> bool:
        return (chat_id, user_id) in self.members

    def add_member(self, chat_id: str, user_id: str) -> None:
        self.members.add((chat_id, user_id))
        self.added.append((chat_id, user_id))


class _Requests:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    def upsert_request(self, chat_id: str, requester_user_id: str, *, message: str | None = None) -> dict:
        row = {
            "id": f"chat_join:{chat_id}:{requester_user_id}",
            "chat_id": chat_id,
            "requester_user_id": requester_user_id,
            "state": "pending",
            "message": message,
            "created_at": 1.0,
            "updated_at": 1.0,
        }
        self.rows[row["id"]] = row
        return row

    def get_by_id(self, request_id: str) -> dict | None:
        return self.rows.get(request_id)

    def list_for_chat(self, chat_id: str) -> list[dict]:
        return [row for row in self.rows.values() if row["chat_id"] == chat_id]

    def set_state(self, request_id: str, *, state: str, decided_by_user_id: str) -> dict:
        row = self.rows[request_id]
        row.update({"state": state, "decided_by_user_id": decided_by_user_id, "updated_at": 2.0})
        return row


class _Messaging:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str, str, list[str] | None]] = []

    def send(self, chat_id: str, sender_id: str, content: str, *, message_type: str, mentions=None) -> dict:
        self.sent.append((chat_id, sender_id, content, message_type, mentions))
        return {"id": "msg-1"}

    def resolve_display_user(self, user_id: str):
        if user_id == "visitor-1":
            return SimpleNamespace(id="visitor-1", display_name="Visitor One", type="external")
        return None


def _service() -> tuple[ChatJoinRequestService, _Members, _Requests, _Messaging]:
    members = _Members()
    requests = _Requests()
    messaging = _Messaging()
    chats = SimpleNamespace(
        get_by_id=lambda chat_id: (
            SimpleNamespace(
                id=chat_id,
                type="group",
                title="Group",
                status="active",
                created_by_user_id="owner-1",
            )
            if chat_id == "chat-1"
            else None
        )
    )
    return (
        ChatJoinRequestService(
            chat_repo=chats,
            chat_member_repo=members,
            chat_join_request_repo=requests,
            messaging_service=messaging,
        ),
        members,
        requests,
        messaging,
    )


def test_chat_join_request_records_pending_row_and_notifies_owner() -> None:
    service, _members, _requests, messaging = _service()

    row = service.request("chat-1", "visitor-1", "please add me")

    assert row["id"] == "chat_join:chat-1:visitor-1"
    assert row["state"] == "pending"
    assert messaging.sent == [
        (
            "chat-1",
            "visitor-1",
            "visitor-1 requested to join this chat: please add me",
            "notification",
            ["owner-1"],
        )
    ]


def test_chat_join_request_list_projects_requester_display_fields() -> None:
    service, _members, requests, _messaging = _service()
    requests.rows["chat_join:chat-1:visitor-1"] = {
        "id": "chat_join:chat-1:visitor-1",
        "chat_id": "chat-1",
        "requester_user_id": "visitor-1",
        "state": "pending",
        "message": "please add me",
        "created_at": 1.0,
        "updated_at": 1.0,
    }

    rows = service.list_for_chat("chat-1", "owner-1")

    assert rows == [
        {
            "id": "chat_join:chat-1:visitor-1",
            "chat_id": "chat-1",
            "requester_user_id": "visitor-1",
            "requester_name": "Visitor One",
            "requester_type": "external",
            "state": "pending",
            "message": "please add me",
            "created_at": 1.0,
            "updated_at": 1.0,
        }
    ]


def test_chat_join_target_exposes_minimal_non_member_state() -> None:
    service, _members, requests, _messaging = _service()
    requests.rows["chat_join:chat-1:visitor-1"] = {
        "id": "chat_join:chat-1:visitor-1",
        "chat_id": "chat-1",
        "requester_user_id": "visitor-1",
        "state": "pending",
        "message": "please add me",
        "created_at": 1.0,
        "updated_at": 1.0,
    }

    target = service.join_target("chat-1", "visitor-1")

    assert target == {
        "id": "chat-1",
        "type": "group",
        "title": "Group",
        "status": "active",
        "created_by_user_id": "owner-1",
        "is_member": False,
        "current_request": {
            "id": "chat_join:chat-1:visitor-1",
            "chat_id": "chat-1",
            "requester_user_id": "visitor-1",
            "requester_name": "Visitor One",
            "requester_type": "external",
            "state": "pending",
            "message": "please add me",
            "created_at": 1.0,
            "updated_at": 1.0,
        },
    }


def test_chat_join_approve_requires_owner_and_adds_member_before_notification() -> None:
    service, members, _requests, messaging = _service()
    pending = service.request("chat-1", "visitor-1", "please add me")

    row = service.approve("chat-1", pending["id"], "owner-1")

    assert row["state"] == "approved"
    assert members.added == [("chat-1", "visitor-1")]
    assert messaging.sent[-1] == (
        "chat-1",
        "owner-1",
        "Approved chat join request for visitor-1.",
        "notification",
        ["visitor-1"],
    )


def test_chat_join_approve_rejects_non_owner() -> None:
    service, _members, _requests, _messaging = _service()
    pending = service.request("chat-1", "visitor-1", "please add me")

    with pytest.raises(PermissionError):
        service.approve("chat-1", pending["id"], "visitor-1")
