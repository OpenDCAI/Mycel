from __future__ import annotations

import pytest
from pydantic import ValidationError

from storage.contracts import ChatMemberRow, ChatRow, ContactEdgeRow, MessageRow, RelationshipRow


def test_chat_row_requires_type_and_creator() -> None:
    row = ChatRow(
        id="chat-1",
        type="group",
        created_by_user_id="user-1",
        created_at=1.0,
    )

    assert row.type == "group"
    assert row.created_by_user_id == "user-1"
    assert row.next_message_seq == 0


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("chat_id", "", "chat_member.chat_id must not be blank"),
        ("user_id", "", "chat_member.user_id must not be blank"),
    ],
)
def test_chat_member_identity_fields_fail_loudly(field: str, value: object, expected: str) -> None:
    payload = {
        "chat_id": "chat-1",
        "user_id": "user-1",
        "joined_at": 1.0,
    }
    payload[field] = value

    with pytest.raises(ValidationError, match=expected):
        ChatMemberRow(**payload)


def test_chat_member_last_read_seq_must_be_non_negative() -> None:
    with pytest.raises(ValidationError, match="chat_member.last_read_seq must be >= 0"):
        ChatMemberRow(chat_id="chat-1", user_id="user-1", joined_at=1.0, last_read_seq=-1)


def test_message_row_requires_user_sender_and_positive_seq() -> None:
    row = MessageRow(
        id="msg-1",
        chat_id="chat-1",
        seq=1,
        sender_user_id="user-1",
        content="hello",
        created_at=1.0,
    )

    assert row.sender_user_id == "user-1"
    assert row.seq == 1
    assert row.content_type == "text/plain"
    assert row.message_type == "text"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {
                "id": "msg-1",
                "chat_id": "chat-1",
                "seq": 0,
                "sender_user_id": "user-1",
                "content": "hello",
                "created_at": 1.0,
            },
            "message.seq must be >= 1",
        ),
        (
            {
                "id": "msg-1",
                "chat_id": "chat-1",
                "seq": 1,
                "sender_user_id": "",
                "content": "hello",
                "created_at": 1.0,
            },
            "message.sender_user_id must not be blank",
        ),
    ],
)
def test_message_row_identity_failures(payload: dict[str, object], expected: str) -> None:
    with pytest.raises(ValidationError, match=expected):
        MessageRow(**payload)


def test_contact_edge_row_is_directed_and_user_bound() -> None:
    row = ContactEdgeRow(
        source_user_id="user-a",
        target_user_id="user-b",
        kind="hire",
        state="pending",
        created_at=1.0,
    )

    assert row.source_user_id == "user-a"
    assert row.target_user_id == "user-b"
    assert row.kind == "hire"
    assert row.state == "pending"


def test_relationship_row_requires_sorted_pair() -> None:
    with pytest.raises(ValidationError, match="relationship.user_low must be < relationship.user_high"):
        RelationshipRow(
            user_low="user-z",
            user_high="user-a",
            kind="friend",
            initiator_user_id="user-z",
            created_at=1.0,
        )
