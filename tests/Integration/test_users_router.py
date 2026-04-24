from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.web.core.dependencies import get_current_user_id
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
    default_threads: dict[str, dict[str, object] | None] | None = None,
) -> SimpleNamespace:
    relationships = relationships or {}
    default_threads = default_threads or {}
    relationship_service = SimpleNamespace(
        list_for_user=lambda _user_id: [
            SimpleNamespace(other_user_id=other_user_id, state=state) for other_user_id, state in relationships.items()
        ]
    )
    chat_runtime_state = SimpleNamespace(
        relationship_service=relationship_service,
        contact_repo=contact_repo or _empty_contact_repo(),
    )
    return SimpleNamespace(
        state=SimpleNamespace(
            user_repo=SimpleNamespace(list_all=lambda: users),
            thread_repo=SimpleNamespace(get_default_thread=lambda agent_user_id: default_threads.get(agent_user_id)),
            chat_runtime_state=chat_runtime_state,
        )
    )


def _list_chat_candidates(app: SimpleNamespace, *, user_id: str = "u1"):
    return users_router.list_chat_candidates(
        user_id=user_id,
        user_repo=app.state.user_repo,
        relationship_service=getattr(app.state.chat_runtime_state, "relationship_service", None),
        contact_repo=getattr(app.state.chat_runtime_state, "contact_repo", None),
        thread_repo=getattr(app.state, "thread_repo", None),
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

    result = await _list_chat_candidates(app)

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

    result = await _list_chat_candidates(app)

    assert result[0]["user_id"] == "a-owned"
    assert result[0]["is_owned"] is True
    assert result[0]["relationship_state"] == "none"
    assert result[0]["can_chat"] is True


@pytest.mark.asyncio
async def test_list_chat_candidates_exposes_default_thread_id_for_owned_agents_only():
    app = _users_app(
        [_human("u1", "owner"), _agent("a-owned-ready", "Ready Agent", "u1"), _agent("a-owned-cold", "Cold Agent", "u1")],
        default_threads={
            "a-owned-ready": {"id": "thread-ready"},
            "a-owned-cold": None,
        },
    )

    result = await _list_chat_candidates(app)

    ready = next(item for item in result if item["user_id"] == "a-owned-ready")
    cold = next(item for item in result if item["user_id"] == "a-owned-cold")
    assert ready["default_thread_id"] == "thread-ready"
    assert cold["default_thread_id"] is None


@pytest.mark.asyncio
async def test_list_chat_candidates_fails_loud_when_owned_agent_threads_need_thread_repo():
    app = SimpleNamespace(
        state=SimpleNamespace(
            user_repo=SimpleNamespace(list_all=lambda: [_human("u1", "owner"), _agent("a-owned", "Morel", "u1")]),
            chat_runtime_state=SimpleNamespace(
                relationship_service=SimpleNamespace(list_for_user=lambda _user_id: []),
                contact_repo=_empty_contact_repo(),
            ),
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await _list_chat_candidates(app)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Thread repo unavailable"


@pytest.mark.asyncio
async def test_list_chat_candidates_marks_normal_active_contacts_as_chat_candidates():
    app = _users_app(
        [_human("u1", "owner"), _human("u2", "other")],
        contact_repo=_active_contact_repo("u1", "u2"),
    )

    result = await _list_chat_candidates(app)

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

    result = await _list_chat_candidates(app)

    human_item = next(item for item in result if item["user_id"] == "u2")
    agent_item = next(item for item in result if item["user_id"] == "a-other")
    assert human_item["can_chat"] is True
    assert agent_item["owner_name"] == "other"
    assert agent_item["relationship_state"] == "none"
    assert agent_item["can_chat"] is True


@pytest.mark.asyncio
async def test_list_chat_candidates_fails_loud_when_relationship_service_missing():
    app = SimpleNamespace(
        state=SimpleNamespace(
            user_repo=SimpleNamespace(list_all=lambda: [_human("u1", "owner"), _human("u2", "other")]),
            thread_repo=SimpleNamespace(get_default_thread=lambda _agent_user_id: None),
            chat_runtime_state=SimpleNamespace(contact_repo=_empty_contact_repo()),
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await _list_chat_candidates(app)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "chat bootstrap not attached: relationship_service"


@pytest.mark.asyncio
async def test_list_chat_candidates_fails_loud_when_contact_repo_missing():
    app = SimpleNamespace(
        state=SimpleNamespace(
            user_repo=SimpleNamespace(list_all=lambda: [_human("u1", "owner"), _human("u2", "other")]),
            thread_repo=SimpleNamespace(get_default_thread=lambda _agent_user_id: None),
            chat_runtime_state=SimpleNamespace(
                relationship_service=SimpleNamespace(list_for_user=lambda _user_id: []),
            ),
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await _list_chat_candidates(app)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "chat bootstrap not attached: contact_repo"


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


def test_user_router_exposes_chat_candidates_route():
    paths = {route.path for route in users_router.users_router.routes}

    assert "/api/users/chat-candidates" in paths


def test_chat_candidates_route_reads_dependencies_from_app_state() -> None:
    owner = _human("u1", "owner")
    other = _human("u2", "other")
    app = FastAPI()
    app.include_router(users_router.users_router)
    app.state.user_repo = SimpleNamespace(list_all=lambda: [owner, other])
    app.state.thread_repo = SimpleNamespace(get_default_thread=lambda _agent_user_id: None)
    relationship_service = SimpleNamespace(list_for_user=lambda _user_id: [SimpleNamespace(other_user_id="u2", state="visit")])
    contact_repo = _empty_contact_repo()
    app.state.chat_runtime_state = SimpleNamespace(
        relationship_service=relationship_service,
        contact_repo=contact_repo,
    )
    app.dependency_overrides[get_current_user_id] = lambda: "u1"

    with TestClient(app) as client:
        response = client.get("/api/users/chat-candidates", headers={"Authorization": "Bearer token"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "user_id": "u2",
            "name": "other",
            "type": "human",
            "avatar_url": None,
            "owner_name": None,
            "agent_name": "other",
            "is_owned": False,
            "relationship_state": "visit",
            "can_chat": True,
        }
    ]


def test_chat_candidates_route_exposes_owned_agent_default_thread_id() -> None:
    owner = _human("u1", "owner")
    owned_agent = _agent("a-owned", "Ready Agent", "u1")
    app = FastAPI()
    app.include_router(users_router.users_router)
    app.state.user_repo = SimpleNamespace(list_all=lambda: [owner, owned_agent])
    app.state.thread_repo = SimpleNamespace(
        get_default_thread=lambda agent_user_id: {"id": "thread-ready"} if agent_user_id == "a-owned" else None
    )
    relationship_service = SimpleNamespace(list_for_user=lambda _user_id: [])
    contact_repo = _empty_contact_repo()
    app.state.chat_runtime_state = SimpleNamespace(
        relationship_service=relationship_service,
        contact_repo=contact_repo,
    )
    app.dependency_overrides[get_current_user_id] = lambda: "u1"

    with TestClient(app) as client:
        response = client.get("/api/users/chat-candidates", headers={"Authorization": "Bearer token"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "user_id": "a-owned",
            "name": "Ready Agent",
            "type": "agent",
            "avatar_url": None,
            "owner_name": "owner",
            "agent_name": "Ready Agent",
            "is_owned": True,
            "relationship_state": "none",
            "can_chat": True,
            "default_thread_id": "thread-ready",
        }
    ]


def test_chat_candidates_route_fails_loud_when_contact_repo_missing() -> None:
    owner = _human("u1", "owner")
    other = _human("u2", "other")
    app = FastAPI()
    app.include_router(users_router.users_router)
    app.state.user_repo = SimpleNamespace(list_all=lambda: [owner, other])
    app.state.thread_repo = SimpleNamespace(get_default_thread=lambda _agent_user_id: None)
    relationship_service = SimpleNamespace(list_for_user=lambda _user_id: [])
    app.state.chat_runtime_state = SimpleNamespace(
        relationship_service=relationship_service,
        contact_repo=None,
    )
    app.dependency_overrides[get_current_user_id] = lambda: "u1"

    with TestClient(app) as client:
        response = client.get("/api/users/chat-candidates", headers={"Authorization": "Bearer token"})

    assert response.status_code == 503
    assert response.json() == {"detail": "chat bootstrap not attached: contact_repo"}


@pytest.mark.asyncio
async def test_list_chat_candidates_projects_external_user_like_unowned_participant() -> None:
    current_user = _human("u1", "owner")
    external_user = UserRow(id="ext-1", display_name="Codex External", type=UserType.EXTERNAL, created_at=NOW)
    app = _users_app([current_user, external_user], relationships={"ext-1": "visit"})

    result = await _list_chat_candidates(app)

    assert result == [
        {
            "user_id": "ext-1",
            "name": "Codex External",
            "type": "external",
            "avatar_url": None,
            "owner_name": None,
            "agent_name": "Codex External",
            "is_owned": False,
            "relationship_state": "visit",
            "can_chat": True,
        }
    ]
