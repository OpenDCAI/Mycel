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
                get_by_user_id=lambda _uid: (_ for _ in ()).throw(
                    AssertionError("visit rows should use messaging summary, not thread fallback")
                ),
            ),
            agent_pool={},
            thread_last_active={},
            messaging_service=SimpleNamespace(
                list_conversation_summaries_for_user=lambda _user_id: [
                    {
                        "id": "chat-1",
                        "title": "Toad",
                        "avatar_url": avatar_url("agent-user-1", False),
                        "updated_at": "2026-04-07T00:00:00Z",
                        "unread_count": 3,
                        "entities": [
                            {
                                "id": "thread-user-1",
                                "name": "Toad",
                                "type": "agent",
                                "avatar_url": avatar_url("agent-user-1", False),
                            }
                        ],
                    }
                ],
                list_chats_for_user=lambda _user_id: (_ for _ in ()).throw(
                    AssertionError("conversation sidebar must use lightweight chat summaries")
                ),
            ),
            user_repo=SimpleNamespace(
                get_by_id=lambda _uid: (_ for _ in ()).throw(AssertionError("router should not batch resolve users"))
            ),
            chat_repo=SimpleNamespace(
                get_by_id=lambda _chat_id: (_ for _ in ()).throw(AssertionError("router should not rebuild chat summary"))
            ),
            messages_repo=SimpleNamespace(
                count_unread=lambda _chat_id, _user_id: (_ for _ in ()).throw(AssertionError("router should not recount unread"))
            ),
        )
    )

    result = await conversations_router.list_conversations("human-user-1", app=app)

    assert result == [
        {
            "id": "chat-1",
            "type": "visit",
            "title": "Toad",
            "avatar_url": avatar_url("agent-user-1", False),
            "updated_at": "2026-04-07T00:00:00Z",
            "unread_count": 3,
            "running": False,
        }
    ]


@pytest.mark.asyncio
async def test_list_conversations_sorts_mixed_updated_at_types_without_type_error() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(
                list_by_owner_user_id=lambda _user_id: [
                    {
                        "id": "thread-1",
                        "agent_user_id": "agent-user-1",
                        "agent_name": "Morel",
                        "agent_avatar": None,
                        "sandbox_type": "local",
                    }
                ],
                get_by_user_id=lambda _uid: None,
            ),
            agent_pool={},
            thread_last_active={"thread-1": 1775540000.0},
            messaging_service=SimpleNamespace(
                list_conversation_summaries_for_user=lambda _user_id: [
                    {
                        "id": "chat-1",
                        "title": "Toad",
                        "avatar_url": avatar_url("member-agent-2", False),
                        "updated_at": 1775540100.0,
                        "unread_count": 0,
                        "entities": [
                            {
                                "id": "member-agent-2",
                                "name": "Toad",
                                "type": "agent",
                                "avatar_url": avatar_url("member-agent-2", False),
                            }
                        ],
                    }
                ],
                list_chats_for_user=lambda _user_id: (_ for _ in ()).throw(
                    AssertionError("conversation sidebar must use lightweight chat summaries")
                ),
            ),
            user_repo=SimpleNamespace(
                get_by_id=lambda _uid: (_ for _ in ()).throw(AssertionError("router should not batch resolve users"))
            ),
            chat_repo=SimpleNamespace(
                get_by_id=lambda _chat_id: (_ for _ in ()).throw(AssertionError("router should not rebuild chat summary"))
            ),
            messages_repo=SimpleNamespace(
                count_unread=lambda _chat_id, _user_id: (_ for _ in ()).throw(AssertionError("router should not recount unread"))
            ),
        )
    )

    result = await conversations_router.list_conversations("human-user-1", app=app)

    assert [item["id"] for item in result] == ["chat-1", "thread-1"]


@pytest.mark.asyncio
async def test_list_conversations_hire_entries_do_not_leak_template_member_ids() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(
                list_by_owner_user_id=lambda _user_id: [
                    {
                        "id": "thread-1",
                        "agent_user_id": "agent-user-1",
                        "agent_name": "Morel",
                        "agent_avatar": "avatars/morel.png",
                        "sandbox_type": "local",
                    }
                ],
                get_by_user_id=lambda _uid: None,
            ),
            agent_pool={},
            thread_last_active={},
            messaging_service=None,
        )
    )

    result = await conversations_router.list_conversations("human-user-1", app=app)

    assert result == [
        {
            "id": "thread-1",
            "type": "hire",
            "title": "Morel",
            "avatar_url": avatar_url("agent-user-1", True),
            "updated_at": None,
            "unread_count": 0,
            "running": False,
        }
    ]
    assert "member_id" not in result[0]


@pytest.mark.asyncio
async def test_list_conversations_does_not_require_member_repo() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(
                list_by_owner_user_id=lambda _user_id: [],
                get_by_user_id=lambda _uid: (_ for _ in ()).throw(AssertionError("router should not bridge visit rows itself")),
            ),
            agent_pool={},
            thread_last_active={},
            messaging_service=SimpleNamespace(
                list_conversation_summaries_for_user=lambda _user_id: [
                    {
                        "id": "chat-1",
                        "title": "Morel",
                        "avatar_url": avatar_url("agent-user-1", True),
                        "updated_at": "2026-04-07T00:00:00Z",
                        "unread_count": 0,
                        "entities": [
                            {
                                "id": "thread-user-1",
                                "name": "Morel",
                                "type": "agent",
                                "avatar_url": avatar_url("agent-user-1", True),
                            }
                        ],
                    }
                ],
                list_chats_for_user=lambda _user_id: (_ for _ in ()).throw(
                    AssertionError("conversation sidebar must use lightweight chat summaries")
                ),
            ),
            user_repo=SimpleNamespace(
                get_by_id=lambda _uid: (_ for _ in ()).throw(AssertionError("router should not resolve visit entities"))
            ),
            chat_repo=SimpleNamespace(
                get_by_id=lambda _chat_id: (_ for _ in ()).throw(AssertionError("router should not rebuild chat summary"))
            ),
            messages_repo=SimpleNamespace(
                count_unread=lambda _chat_id, _user_id: (_ for _ in ()).throw(AssertionError("router should not recount unread"))
            ),
        )
    )

    result = await conversations_router.list_conversations("human-user-1", app=app)

    assert result[0]["title"] == "Morel"
    assert result[0]["avatar_url"] == avatar_url("agent-user-1", True)


@pytest.mark.asyncio
async def test_list_conversations_runs_sync_projection_off_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(list_by_owner_user_id=lambda _user_id: []),
            agent_pool={},
            thread_last_active={},
            messaging_service=SimpleNamespace(list_conversation_summaries_for_user=lambda _user_id: []),
        )
    )
    to_thread_calls: list[tuple[str, tuple[object, ...]]] = []

    async def _fake_to_thread(fn, *args):
        to_thread_calls.append((fn.__name__, args))
        return fn(*args)

    monkeypatch.setattr(conversations_router.asyncio, "to_thread", _fake_to_thread)

    assert await conversations_router.list_conversations("human-user-1", app=app) == []
    assert to_thread_calls == [("_list_conversations_for_user", (app, "human-user-1"))]
