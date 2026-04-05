from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.web.routers import connections as connections_router


class _FakeThreadRepo:
    def list_by_owner_user_id(self, _user_id: str):
        return [
            {"id": "thread-user-1", "entity_name": "Toad · 分身1", "member_id": "member-1", "member_avatar": "avatar.png"},
            {"id": "subagent-deadbeef", "entity_name": "internal child", "member_id": "member-1", "member_avatar": None},
        ]


class _FakeChatService:
    def list_chats_for_user(self, _user_id: str):
        return [
            {
                "id": "chat-1",
                "entities": [
                    {"id": "human-1", "name": "You"},
                    {"id": "agent-1", "name": "Morel"},
                ],
            }
        ]


@pytest.mark.asyncio
async def test_wechat_routing_targets_hides_internal_subagent_threads():
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=_FakeThreadRepo(),
            chat_service=_FakeChatService(),
        )
    )

    result = await connections_router.wechat_routing_targets(
        user_id="owner-1",
        app=app,
    )

    assert result["threads"] == [
        {
            "id": "thread-user-1",
            "label": "Toad · 分身1",
            "avatar_url": "/api/members/member-1/avatar",
        }
    ]
