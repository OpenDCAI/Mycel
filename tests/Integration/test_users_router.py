from __future__ import annotations

# NOTE: User is the only identity table. The old EntityRow layer was removed;
# this router projects user rows into chat-candidate payloads for contacts and
# group-chat creation. The test below verifies the current production behaviour:
#   • current user is excluded
#   • other humans and agents are all included (no branch filtering)
#   • chat/contact eligibility is computed by backend ownership + relationship state
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.routers import users as users_router
from storage.contracts import ContactEdgeRow, UserRow, UserType

NOW = 1_775_223_756.0


def _empty_contact_repo() -> SimpleNamespace:
    return SimpleNamespace(list_for_user=lambda _user_id: [])


def _human(user_id: str, name: str) -> UserRow:
    return UserRow(id=user_id, display_name=name, type=UserType.HUMAN, created_at=NOW)


def _agent(user_id: str, name: str, owner_user_id: str) -> UserRow:
    return UserRow(
        id=user_id,
        display_name=name,
        type=UserType.AGENT,
        owner_user_id=owner_user_id,
        agent_config_id=f"cfg-{user_id}",
        created_at=NOW,
    )


def _active_contact_repo(source_user_id: str, target_user_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        list_for_user=lambda _user_id: [
            ContactEdgeRow(
                source_user_id=source_user_id,
                target_user_id=target_user_id,
                kind="normal",
                state="active",
                created_at=NOW,
            )
        ]
    )


def _users_app(
    users: list[UserRow],
    *,
    relationships: dict[str, str] | None = None,
    contact_repo: object | None = None,
) -> SimpleNamespace:
    relationships = relationships or {}
    return SimpleNamespace(
        state=SimpleNamespace(
            user_repo=SimpleNamespace(list_all=lambda: users),
            relationship_service=SimpleNamespace(
                list_for_user=lambda _user_id: [
                    SimpleNamespace(other_user_id=other_user_id, state=state) for other_user_id, state in relationships.items()
                ]
            ),
            contact_repo=contact_repo or _empty_contact_repo(),
        )
    )


@pytest.mark.asyncio
async def test_list_chat_candidates_excludes_current_user_and_returns_all_others():
    current_user = _human("u1", "owner")
    other_human = _human("u2", "other")
    main_agent = _agent("a-main", "Toad", "u2")
    child_agent = _agent("a-child", "Toad Branch", "u2")
    app = _users_app(
        [current_user, other_human, main_agent, child_agent],
        relationships={"u2": "visit", "a-main": "pending"},
    )

    result = await users_router.list_chat_candidates(user_id="u1", app=app)

    # Current user (u1) is excluded; all other users are returned.
    candidates = [(item["type"], item.get("user_id")) for item in result]
    assert candidates == [
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
    assert "default_thread_id" not in human_item
    assert "is_default_thread" not in human_item
    assert "branch_index" not in human_item
    assert human_item["is_owned"] is False
    assert human_item["relationship_state"] == "visit"
    assert human_item["can_chat"] is True

    # Agent entry is keyed by unified user identity, not private thread metadata.
    main_item = next(i for i in result if i.get("user_id") == "a-main")
    assert "id" not in main_item
    assert "member_id" not in main_item
    assert main_item["agent_name"] == "Toad"
    assert "member_name" not in main_item
    assert "default_thread_id" not in main_item
    assert "is_default_thread" not in main_item
    assert "branch_index" not in main_item
    assert main_item["is_owned"] is False
    assert main_item["relationship_state"] == "pending"
    assert main_item["can_chat"] is True

    # Child agent: also returned (frontend decides whether to hide it).
    child_item = next(i for i in result if i.get("user_id") == "a-child")
    assert child_item["agent_name"] == "Toad Branch"
    assert "member_name" not in child_item
    assert "default_thread_id" not in child_item
    assert "is_default_thread" not in child_item
    assert "branch_index" not in child_item
    assert child_item["relationship_state"] == "none"
    assert child_item["can_chat"] is True


@pytest.mark.asyncio
async def test_list_chat_candidates_marks_owned_agents_as_chat_candidates_without_relationship():
    app = _users_app([_human("u1", "owner"), _agent("a-owned", "Morel", "u1")])

    result = await users_router.list_chat_candidates(user_id="u1", app=app)

    assert result[0]["user_id"] == "a-owned"
    assert result[0]["is_owned"] is True
    assert result[0]["relationship_state"] == "none"
    assert result[0]["can_chat"] is True


@pytest.mark.asyncio
async def test_list_chat_candidates_marks_normal_active_contacts_as_chat_candidates():
    app = _users_app(
        [_human("u1", "owner"), _human("u2", "other")],
        contact_repo=_active_contact_repo("u1", "u2"),
    )

    result = await users_router.list_chat_candidates(user_id="u1", app=app)

    assert result == [
        {
            "user_id": "u2",
            "name": "other",
            "type": "human",
            "avatar_url": None,
            "owner_name": None,
            "agent_name": "other",
            "is_owned": False,
            "relationship_state": "none",
            "can_chat": True,
        }
    ]


@pytest.mark.asyncio
async def test_list_chat_candidates_marks_agents_owned_by_active_contacts_as_chat_candidates():
    app = _users_app(
        [_human("u1", "owner"), _human("u2", "other"), _agent("a-other", "Toad", "u2")],
        contact_repo=_active_contact_repo("u1", "u2"),
    )

    result = await users_router.list_chat_candidates(user_id="u1", app=app)

    human_item = next(item for item in result if item["user_id"] == "u2")
    agent_item = next(item for item in result if item["user_id"] == "a-other")
    assert human_item["can_chat"] is True
    assert agent_item["owner_name"] == "other"
    assert agent_item["relationship_state"] == "none"
    assert agent_item["can_chat"] is True


def test_get_user_or_404_returns_user():
    agent = _agent("a-main", "Toad", "u2")
    app = SimpleNamespace(
        state=SimpleNamespace(
            user_repo=SimpleNamespace(get_by_id=lambda user_id: agent if user_id == "a-main" else None),
        )
    )

    result = users_router._get_user_or_404(app, "a-main")

    assert result is agent


def test_get_user_or_404_raises_for_missing_user():
    app = SimpleNamespace(
        state=SimpleNamespace(
            user_repo=SimpleNamespace(get_by_id=lambda _user_id: None),
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        users_router._get_user_or_404(app, "missing")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "User not found"


def test_user_router_exposes_chat_candidates_not_removed_entities_path():
    paths = {route.path for route in users_router.users_router.routes}

    assert "/api/users/chat-candidates" in paths
    assert "/api/users/{user_id}/agent-thread" not in paths
    assert "/api/entities" not in paths
