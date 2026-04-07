from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.models.panel import PublishMemberRequest, UpdateMemberRequest, UpdateProfileRequest
from backend.web.routers import panel as panel_router
from backend.web.services import library_service, member_service, profile_service
from storage.contracts import UserRow, UserType


@pytest.mark.asyncio
async def test_panel_members_uses_injected_user_repo_for_owner_scope(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    agent = UserRow(
        id="agent-1",
        type=UserType.AGENT,
        display_name="Toad",
        owner_user_id="user-1",
        agent_config_id="cfg-1",
        created_at=1.0,
    )
    seen: list[str] = []
    monkeypatch.setattr(
        member_service,
        "_member_to_dict",
        lambda _member_dir: {
            "id": "agent-1",
            "name": "Toad",
            "avatar_url": "avatars/agent-1.png",
            "config": {},
        },
    )
    member_dir = tmp_path / "agent-1"
    member_dir.mkdir()
    (member_dir / "agent.md").write_text("stub", encoding="utf-8")
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)

    fake_repo = SimpleNamespace(
        list_by_owner_user_id=lambda owner_user_id: seen.append(owner_user_id) or [agent],
    )

    result = await panel_router.list_members(
        user_id="user-1",
        request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(user_repo=fake_repo))),
    )

    assert seen == ["user-1"]
    assert result["items"] == [{"id": "agent-1", "name": "Toad", "avatar_url": "avatars/agent-1.png", "config": {}}]


def test_owned_member_helper_returns_member_for_owner(monkeypatch: pytest.MonkeyPatch):
    member = {"id": "agent-1", "name": "Toad"}
    monkeypatch.setattr(member_service, "get_member", lambda member_id: member if member_id == "agent-1" else None)

    result = panel_router._get_owned_member_or_404(
        "agent-1",
        "user-1",
        SimpleNamespace(
            get_by_id=lambda user_id: _agent_user(user_id=user_id) if user_id == "agent-1" else None,
        ),
    )

    assert result == member


def test_owned_member_helper_raises_404_for_missing_member(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(member_service, "get_member", lambda _member_id: None)

    with pytest.raises(HTTPException) as excinfo:
        panel_router._get_owned_member_or_404("missing", "user-1", SimpleNamespace(get_by_id=lambda _user_id: None))

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Member not found"


def test_owned_member_helper_raises_403_for_wrong_owner(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(member_service, "get_member", lambda _member_id: {"id": "agent-1"})

    with pytest.raises(HTTPException) as excinfo:
        panel_router._get_owned_member_or_404(
            "agent-1",
            "user-1",
            SimpleNamespace(get_by_id=lambda _user_id: _agent_user(owner_user_id="user-2")),
        )

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "Forbidden"


@pytest.mark.asyncio
async def test_update_member_route_returns_404_for_missing_member(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(member_service, "get_member", lambda _member_id: None)

    with pytest.raises(HTTPException) as excinfo:
        await panel_router.update_member(
            "missing",
            UpdateMemberRequest(name="new-name"),
            request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(user_repo=SimpleNamespace(get_by_id=lambda _user_id: None)))),
            user_id="user-1",
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Member not found"


@pytest.mark.asyncio
async def test_delete_member_route_keeps_builtin_guard_before_owner_lookup(monkeypatch: pytest.MonkeyPatch):
    def explode(_member_id: str):
        raise AssertionError("member lookup should not run for builtin guard")

    monkeypatch.setattr(member_service, "get_member", explode)

    with pytest.raises(HTTPException) as excinfo:
        await panel_router.delete_member(
            "__leon__",
            request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(user_repo=SimpleNamespace()))),
            user_id="user-1",
        )

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "Cannot delete builtin member"


@pytest.mark.asyncio
async def test_publish_member_route_keeps_builtin_guard_before_owner_lookup(monkeypatch: pytest.MonkeyPatch):
    def explode(_member_id: str):
        raise AssertionError("member lookup should not run for builtin guard")

    monkeypatch.setattr(member_service, "get_member", explode)

    with pytest.raises(HTTPException) as excinfo:
        await panel_router.publish_member(
            "__leon__",
            PublishMemberRequest(),
            request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(user_repo=SimpleNamespace()))),
            user_id="user-1",
        )

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "Cannot publish builtin member"


def test_profile_service_prefers_authenticated_member_over_config_defaults():
    user = UserRow(
        id="user-1",
        type=UserType.HUMAN,
        display_name="codex",
        email="codex@example.com",
        created_at=1.0,
    )

    profile = profile_service.get_profile(user=user)

    assert profile == {"name": "codex", "initials": "CO", "email": "codex@example.com"}


@pytest.mark.asyncio
async def test_profile_route_uses_user_repo_instead_of_member_repo():
    user = UserRow(
        id="user-1",
        type=UserType.HUMAN,
        display_name="codex",
        email="codex@example.com",
        created_at=1.0,
    )

    result = await panel_router.get_profile(
        user_id="user-1",
        request=SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    user_repo=SimpleNamespace(get_by_id=lambda seen_user_id: user if seen_user_id == "user-1" else None),
                    member_repo=SimpleNamespace(
                        get_by_id=lambda _user_id: (_ for _ in ()).throw(AssertionError("member_repo should not back profile shell"))
                    ),
                )
            )
        ),
    )

    assert result == {"name": "codex", "initials": "CO", "email": "codex@example.com"}


def test_profile_service_updates_user_repo_shell_fields_only():
    seen: list[tuple[str, dict[str, object]]] = []

    class _UserRepo:
        def update(self, user_id: str, **fields):
            seen.append((user_id, fields))

        def get_by_id(self, user_id: str):
            if user_id != "user-1":
                return None
            return UserRow(
                id="user-1",
                type=UserType.HUMAN,
                display_name="renamed",
                email="renamed@example.com",
                created_at=1.0,
                updated_at=2.0,
            )

    profile = profile_service.update_profile(
        user_repo=_UserRepo(),
        user_id="user-1",
        name="renamed",
        initials="RN",
        email="renamed@example.com",
    )

    assert seen == [("user-1", {"display_name": "renamed", "email": "renamed@example.com"})]
    assert profile == {"name": "renamed", "initials": "RE", "email": "renamed@example.com"}


@pytest.mark.asyncio
async def test_update_profile_route_uses_user_repo_instead_of_config_file():
    seen: list[tuple[str, dict[str, object]]] = []

    class _UserRepo:
        def update(self, user_id: str, **fields):
            seen.append((user_id, fields))

        def get_by_id(self, user_id: str):
            if user_id != "user-1":
                return None
            return UserRow(
                id="user-1",
                type=UserType.HUMAN,
                display_name="renamed",
                email="renamed@example.com",
                created_at=1.0,
                updated_at=2.0,
            )

    result = await panel_router.update_profile(
        UpdateProfileRequest(name="renamed", initials="RN", email="renamed@example.com"),
        request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(user_repo=_UserRepo()))),
        user_id="user-1",
    )

    assert seen == [("user-1", {"display_name": "renamed", "email": "renamed@example.com"})]
    assert result == {"name": "renamed", "initials": "RE", "email": "renamed@example.com"}


def test_library_service_get_resource_used_by_scopes_to_owner(monkeypatch: pytest.MonkeyPatch):
    seen: list[tuple[str, object]] = []

    monkeypatch.setattr(
        member_service,
        "list_members",
        lambda owner_user_id=None, user_repo=None: (
            seen.append((owner_user_id, user_repo))
            or [
                {"id": "agent-1", "name": "Toad", "config": {"skills": [{"name": "skill-a"}]}},
                {"id": "agent-2", "name": "Dryad", "config": {"skills": [{"name": "skill-b"}]}},
            ]
        ),
    )

    result = library_service.get_resource_used_by("skill", "skill-a", "user-1", user_repo="repo-1")

    assert result == ["Toad"]
    assert seen == [("user-1", "repo-1")]


@pytest.mark.asyncio
async def test_panel_library_used_by_route_uses_user_scope(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        library_service,
        "get_resource_used_by",
        lambda resource_type, resource_name, owner_user_id, user_repo=None: (
            seen.update(
                {
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "owner_user_id": owner_user_id,
                    "user_repo": user_repo,
                }
            )
            or ["Toad"]
        ),
    )

    fake_user_repo = SimpleNamespace()
    result = await panel_router.get_used_by(
        "skill",
        "skill-a",
        request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(user_repo=fake_user_repo))),
        user_id="user-1",
    )

    assert result == {"count": 1, "users": ["Toad"]}
    assert seen == {
        "resource_type": "skill",
        "resource_name": "skill-a",
        "owner_user_id": "user-1",
        "user_repo": fake_user_repo,
    }


def test_builtin_member_surface_exposes_chat_tools():
    member = member_service._leon_builtin()
    tools = {item["name"]: item for item in member["config"]["tools"]}

    for tool_name in ("list_chats", "read_messages", "send_message", "search_messages"):
        assert tool_name in tools
        assert tools[tool_name]["enabled"] is True
        assert tools[tool_name]["group"] == "chat"

    for removed_name in ("chats", "read_message", "search_message", "directory", "wechat_send", "wechat_contacts"):
        assert removed_name not in tools


def _agent_user(*, user_id: str = "agent-1", owner_user_id: str = "user-1") -> UserRow:
    return UserRow(
        id=user_id,
        type=UserType.AGENT,
        display_name="Toad",
        owner_user_id=owner_user_id,
        agent_config_id="cfg-1",
        created_at=1.0,
    )
