from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.web.routers import panel as panel_router
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
