from __future__ import annotations

from types import SimpleNamespace
from typing import cast

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
    delivered: list[str] = []
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
        delivery_fn=lambda member, *_args, **_kwargs: delivered.append(member.id),
    )

    service._deliver_to_agents("chat-1", "human-user-1", "hello", [])

    assert delivered == ["agent-user-1"]


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
