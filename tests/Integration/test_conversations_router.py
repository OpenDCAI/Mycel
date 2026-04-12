from __future__ import annotations

import threading
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
                    AssertionError("visit rows should use messaging summary, not thread lookup")
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
                        "members": [
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
                        "avatar_url": avatar_url("agent-user-2", False),
                        "updated_at": 1775540100.0,
                        "unread_count": 0,
                        "members": [
                            {
                                "id": "agent-user-2",
                                "name": "Toad",
                                "type": "agent",
                                "avatar_url": avatar_url("agent-user-2", False),
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
async def test_list_conversations_collapses_hire_threads_to_one_visible_conversation_per_agent_user() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(
                list_by_owner_user_id=lambda _user_id: [
                    {
                        "id": "thread-main",
                        "agent_user_id": "agent-user-1",
                        "agent_name": "Morel",
                        "agent_avatar": "avatars/morel.png",
                        "sandbox_type": "local",
                        "is_main": True,
                        "branch_index": 0,
                    },
                    {
                        "id": "thread-extra",
                        "agent_user_id": "agent-user-1",
                        "agent_name": "Morel",
                        "agent_avatar": "avatars/morel.png",
                        "sandbox_type": "local",
                        "is_main": False,
                        "branch_index": 1,
                    },
                ],
            ),
            agent_pool={},
            thread_last_active={"thread-main": 1775540000.0, "thread-extra": 1775541000.0},
            messaging_service=None,
        )
    )

    result = await conversations_router.list_conversations("human-user-1", app=app)

    assert [(item["id"], item["title"]) for item in result] == [("thread-main", "Morel")]


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
                        "members": [
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
                get_by_id=lambda _uid: (_ for _ in ()).throw(AssertionError("router should not resolve visit participants"))
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
    assert to_thread_calls == [
        ("_list_hire_conversations_for_user", (app, "human-user-1")),
        ("_list_visit_conversations_for_user", (app, "human-user-1")),
    ]


@pytest.mark.asyncio
async def test_list_conversations_fetches_hire_and_visit_sources_in_parallel() -> None:
    hire_started = threading.Event()
    visit_started = threading.Event()

    def _list_threads(_user_id: str):
        hire_started.set()
        if not visit_started.wait(0.2):
            raise AssertionError("visit summaries did not start while hire threads were loading")
        return []

    def _list_visit_summaries(_user_id: str):
        visit_started.set()
        if not hire_started.wait(0.2):
            raise AssertionError("hire threads did not start while visit summaries were loading")
        return []

    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(list_by_owner_user_id=_list_threads),
            agent_pool={},
            thread_last_active={},
            messaging_service=SimpleNamespace(list_conversation_summaries_for_user=_list_visit_summaries),
        )
    )

    assert await conversations_router.list_conversations("human-user-1", app=app) == []
