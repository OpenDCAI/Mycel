from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.web.routers import conversations as conversations_router
from backend.web.utils.serializers import avatar_url


@pytest.mark.asyncio
async def test_list_conversations_resolves_thread_user_participant_title_and_avatar() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(
                list_by_owner_user_id=lambda _user_id: [],
                get_by_user_id=lambda uid: {"id": "thread-1", "member_id": "member-agent-1"} if uid == "thread-user-1" else None,
            ),
            agent_pool={},
            thread_last_active={},
            messaging_service=SimpleNamespace(
                list_chats_for_user=lambda _user_id: [{"id": "chat-1"}],
                list_chat_members=lambda _chat_id: [
                    {"user_id": "human-user-1"},
                    {"user_id": "thread-user-1"},
                ],
            ),
            member_repo=SimpleNamespace(
                get_by_id=lambda uid: (
                    None
                    if uid == "thread-user-1"
                    else SimpleNamespace(id=uid, name="Toad", avatar=None)
                    if uid == "member-agent-1"
                    else None
                )
            ),
            chat_repo=SimpleNamespace(
                get_by_id=lambda _chat_id: SimpleNamespace(id="chat-1", title=None, created_at="2026-04-07T00:00:00Z")
            ),
            messages_repo=SimpleNamespace(count_unread=lambda _chat_id, _user_id: 3),
        )
    )

    result = await conversations_router.list_conversations("human-user-1", app=app)

    assert result == [
        {
            "id": "chat-1",
            "type": "visit",
            "title": "Toad",
            "member_id": None,
            "avatar_url": avatar_url("member-agent-1", False),
            "updated_at": "2026-04-07T00:00:00Z",
            "unread_count": 3,
            "running": False,
        }
    ]
