from __future__ import annotations

# NOTE: EntityRow was deleted from storage/contracts.py in the entity→member
# refactor (commit cc156856). The old test asserted that child agent branches
# were filtered out on the backend; that filtering was removed along with the
# entity layer — it is now the frontend's responsibility. The test below
# verifies the current production behaviour of list_entities:
#   • current user is excluded
#   • other humans and agents are all included (no branch filtering)
#   • thread metadata (is_main, branch_index) is attached from thread_repo
#   • chat/contact eligibility is computed by backend ownership + relationship state
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.routers import entities as entities_router
from storage.contracts import ContactEdgeRow, UserRow, UserType


def _empty_contact_repo() -> SimpleNamespace:
    return SimpleNamespace(list_for_user=lambda _user_id: [])


@pytest.mark.asyncio
async def test_list_entities_excludes_current_user_and_returns_all_others():
    now = 1_775_223_756.0
    current_user = UserRow(id="u1", display_name="owner", type=UserType.HUMAN, created_at=now)
    other_human = UserRow(id="u2", display_name="other", type=UserType.HUMAN, created_at=now)
    main_agent = UserRow(
        id="a-main",
        display_name="Toad",
        type=UserType.AGENT,
        owner_user_id="u2",
        agent_config_id="cfg-a-main",
        created_at=now,
    )
    child_agent = UserRow(
        id="a-child",
        display_name="Toad Branch",
        type=UserType.AGENT,
        owner_user_id="u2",
        agent_config_id="cfg-a-child",
        created_at=now,
    )

    app = SimpleNamespace(
        state=SimpleNamespace(
            user_repo=SimpleNamespace(list_all=lambda: [current_user, other_human, main_agent, child_agent]),
            thread_repo=SimpleNamespace(
                get_default_thread=lambda user_id: (
                    {"id": "thread-main", "is_main": True, "branch_index": 0}
                    if user_id == "a-main"
                    else {"id": "thread-child", "is_main": False, "branch_index": 1}
                )
            ),
            relationship_service=SimpleNamespace(
                list_for_user=lambda _user_id: [
                    SimpleNamespace(other_user_id="u2", state="visit"),
                    SimpleNamespace(other_user_id="a-main", state="pending"),
                ]
            ),
            contact_repo=_empty_contact_repo(),
        )
    )

    result = await entities_router.list_entities(user_id="u1", app=app)

    # Current user (u1) is excluded; all other users are returned.
    identities = [(item["type"], item.get("user_id")) for item in result]
    assert identities == [
        ("human", "u2"),
        ("agent", "a-main"),
        ("agent", "a-child"),
    ]

    # Human entry is keyed by social user identity, not a generic mixed id.
    human_item = next(i for i in result if i["user_id"] == "u2")
    assert human_item["type"] == "human"
    assert "id" not in human_item
    assert human_item["agent_name"] == "other"
    assert "member_name" not in human_item
    assert human_item["default_thread_id"] is None
    assert human_item["is_owned"] is False
    assert human_item["relationship_state"] == "visit"
    assert human_item["can_chat"] is True

    # Agent entry is keyed by unified user identity plus explicit default thread.
    main_item = next(i for i in result if i.get("user_id") == "a-main")
    assert "id" not in main_item
    assert "member_id" not in main_item
    assert main_item["agent_name"] == "Toad"
    assert "member_name" not in main_item
    assert main_item["default_thread_id"] == "thread-main"
    assert main_item["is_default_thread"] is True
    assert main_item["branch_index"] == 0
    assert main_item["is_owned"] is False
    assert main_item["relationship_state"] == "pending"
    assert main_item["can_chat"] is False

    # Child agent: also returned (frontend decides whether to hide it).
    child_item = next(i for i in result if i.get("user_id") == "a-child")
    assert child_item["agent_name"] == "Toad Branch"
    assert "member_name" not in child_item
    assert child_item["default_thread_id"] == "thread-child"
    assert child_item["is_default_thread"] is False
    assert child_item["branch_index"] == 1
    assert child_item["relationship_state"] == "none"
    assert child_item["can_chat"] is False


@pytest.mark.asyncio
async def test_list_entities_marks_owned_agents_as_chat_candidates_without_relationship():
    now = 1_775_223_756.0
    current_user = UserRow(id="u1", display_name="owner", type=UserType.HUMAN, created_at=now)
    owned_agent = UserRow(
        id="a-owned",
        display_name="Morel",
        type=UserType.AGENT,
        owner_user_id="u1",
        agent_config_id="cfg-a-owned",
        created_at=now,
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            user_repo=SimpleNamespace(list_all=lambda: [current_user, owned_agent]),
            thread_repo=SimpleNamespace(get_default_thread=lambda _user_id: {"id": "thread-owned", "is_main": True, "branch_index": 0}),
            relationship_service=SimpleNamespace(list_for_user=lambda _user_id: []),
            contact_repo=_empty_contact_repo(),
        )
    )

    result = await entities_router.list_entities(user_id="u1", app=app)

    assert result[0]["user_id"] == "a-owned"
    assert result[0]["is_owned"] is True
    assert result[0]["relationship_state"] == "none"
    assert result[0]["can_chat"] is True


@pytest.mark.asyncio
async def test_list_entities_marks_normal_active_contacts_as_chat_candidates():
    now = 1_775_223_756.0
    current_user = UserRow(id="u1", display_name="owner", type=UserType.HUMAN, created_at=now)
    other_human = UserRow(id="u2", display_name="other", type=UserType.HUMAN, created_at=now)
    app = SimpleNamespace(
        state=SimpleNamespace(
            user_repo=SimpleNamespace(list_all=lambda: [current_user, other_human]),
            thread_repo=SimpleNamespace(get_default_thread=lambda _user_id: None),
            relationship_service=SimpleNamespace(list_for_user=lambda _user_id: []),
            contact_repo=SimpleNamespace(
                list_for_user=lambda _user_id: [
                    ContactEdgeRow(
                        source_user_id="u1",
                        target_user_id="u2",
                        kind="normal",
                        state="active",
                        created_at=now,
                    )
                ]
            ),
        )
    )

    result = await entities_router.list_entities(user_id="u1", app=app)

    assert result == [
        {
            "user_id": "u2",
            "name": "other",
            "type": "human",
            "avatar_url": None,
            "owner_name": None,
            "agent_name": "other",
            "default_thread_id": None,
            "is_default_thread": None,
            "branch_index": None,
            "is_owned": False,
            "relationship_state": "none",
            "can_chat": True,
        }
    ]


@pytest.mark.asyncio
async def test_get_agent_thread_reads_main_thread_from_thread_repo_via_user_repo():
    now = 1_775_223_756.0
    agent = UserRow(
        id="a-main",
        display_name="Toad",
        type=UserType.AGENT,
        owner_user_id="u2",
        agent_config_id="cfg-a-main",
        created_at=now,
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            user_repo=SimpleNamespace(get_by_id=lambda user_id: agent if user_id == "a-main" else None),
            thread_repo=SimpleNamespace(
                get_default_thread=lambda user_id: (
                    {"id": "thread-main", "is_main": True, "branch_index": 0} if user_id == "a-main" else None
                )
            ),
        )
    )

    result = await entities_router.get_agent_thread("a-main", current_user_id="u2", app=app)

    assert result == {"user_id": "a-main", "default_thread_id": "thread-main"}


def test_get_user_or_404_returns_user():
    now = 1_775_223_756.0
    agent = UserRow(
        id="a-main",
        display_name="Toad",
        type=UserType.AGENT,
        owner_user_id="u2",
        agent_config_id="cfg-a-main",
        created_at=now,
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            user_repo=SimpleNamespace(get_by_id=lambda user_id: agent if user_id == "a-main" else None),
        )
    )

    result = entities_router._get_user_or_404(app, "a-main")

    assert result is agent


def test_get_user_or_404_raises_for_missing_user():
    app = SimpleNamespace(
        state=SimpleNamespace(
            user_repo=SimpleNamespace(get_by_id=lambda _user_id: None),
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        entities_router._get_user_or_404(app, "missing")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "User not found"
