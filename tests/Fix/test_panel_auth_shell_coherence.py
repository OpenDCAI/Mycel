from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.routers import panel as panel_router
from backend.web.models.panel import PublishMemberRequest, UpdateMemberRequest
from backend.web.services import member_service, profile_service
from storage.contracts import MemberRow, MemberType


@pytest.mark.asyncio
async def test_panel_members_uses_injected_member_repo_for_owner_scope(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    now = 1_775_278_000.0
    agent = MemberRow(
        id="agent-1",
        name="Toad",
        type=MemberType.MYCEL_AGENT,
        owner_user_id="user-1",
        created_at=now,
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
        request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(member_repo=fake_repo))),
    )

    assert seen == ["user-1"]
    assert result["items"] == [{"id": "agent-1", "name": "Toad", "avatar_url": "avatars/agent-1.png", "config": {}}]


def test_owned_member_helper_returns_member_for_owner(monkeypatch: pytest.MonkeyPatch):
    member = {"id": "agent-1", "owner_user_id": "user-1", "name": "Toad"}
    monkeypatch.setattr(member_service, "get_member", lambda member_id: member if member_id == "agent-1" else None)

    result = panel_router._get_owned_member_or_404("agent-1", "user-1")

    assert result == member


def test_owned_member_helper_raises_404_for_missing_member(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(member_service, "get_member", lambda _member_id: None)

    with pytest.raises(HTTPException) as excinfo:
        panel_router._get_owned_member_or_404("missing", "user-1")

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Member not found"


def test_owned_member_helper_raises_403_for_wrong_owner(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        member_service,
        "get_member",
        lambda _member_id: {"id": "agent-1", "owner_user_id": "user-2"},
    )

    with pytest.raises(HTTPException) as excinfo:
        panel_router._get_owned_member_or_404("agent-1", "user-1")

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "Forbidden"


@pytest.mark.asyncio
async def test_update_member_route_returns_404_for_missing_member(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(member_service, "get_member", lambda _member_id: None)

    with pytest.raises(HTTPException) as excinfo:
        await panel_router.update_member(
            "missing",
            UpdateMemberRequest(name="new-name"),
            request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(member_repo=SimpleNamespace()))),
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
            request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
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
            request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
            user_id="user-1",
        )

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "Cannot publish builtin member"


def test_profile_service_prefers_authenticated_member_over_config_defaults():
    member = MemberRow(
        id="user-1",
        name="codex",
        type=MemberType.HUMAN,
        email="codex@example.com",
        created_at=1.0,
    )

    profile = profile_service.get_profile(member=member)

    assert profile == {"name": "codex", "initials": "CO", "email": "codex@example.com"}


def test_builtin_member_surface_exposes_chat_tools():
    member = member_service._leon_builtin()
    tools = {item["name"]: item for item in member["config"]["tools"]}

    for tool_name in ("list_chats", "read_messages", "send_message", "search_messages"):
        assert tool_name in tools
        assert tools[tool_name]["enabled"] is True
        assert tools[tool_name]["group"] == "chat"

    for removed_name in ("chats", "read_message", "search_message", "directory", "wechat_send", "wechat_contacts"):
        assert removed_name not in tools
