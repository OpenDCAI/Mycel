from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from messaging.relationships.service import RelationshipService
from messaging.service import MessagingService


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
