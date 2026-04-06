from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.routers import entities as entities_router


class _FakeUploadFile:
    def __init__(self, content: bytes, *, content_type: str) -> None:
        self._content = content
        self.content_type = content_type

    async def read(self) -> bytes:
        return self._content


def _member(member_id: str, *, owner_user_id: str | None = None, avatar: str | None = None):
    return SimpleNamespace(
        id=member_id,
        owner_user_id=owner_user_id,
        avatar=avatar,
    )


def test_avatar_member_helper_allows_self_or_owner():
    member_repo = SimpleNamespace(
        get_by_id=lambda member_id: _member(member_id, owner_user_id="user-9"),
    )

    self_member = entities_router._get_owned_avatar_member_or_404("user-1", "user-1", member_repo)
    owner_member = entities_router._get_owned_avatar_member_or_404("agent-1", "user-9", member_repo)

    assert self_member.id == "user-1"
    assert owner_member.id == "agent-1"


def test_avatar_member_helper_raises_404_for_missing_member():
    member_repo = SimpleNamespace(get_by_id=lambda _member_id: None)

    with pytest.raises(HTTPException) as excinfo:
        entities_router._get_owned_avatar_member_or_404("missing", "user-1", member_repo)

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Member not found"


def test_avatar_member_helper_raises_403_for_unrelated_user():
    member_repo = SimpleNamespace(
        get_by_id=lambda _member_id: _member("agent-1", owner_user_id="user-2"),
    )

    with pytest.raises(HTTPException) as excinfo:
        entities_router._get_owned_avatar_member_or_404("agent-1", "user-1", member_repo)

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "Not authorized"


@pytest.mark.asyncio
async def test_delete_avatar_route_uses_auth_shell(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    seen: list[tuple[str, object]] = []
    avatar_dir = tmp_path / "avatars"
    avatar_dir.mkdir()
    avatar_path = avatar_dir / "agent-1.png"
    avatar_path.write_bytes(b"png")
    monkeypatch.setattr(entities_router, "AVATARS_DIR", avatar_dir)

    def fake_helper(member_id: str, current_user_id: str, member_repo):
        seen.append(("helper", (member_id, current_user_id)))
        return _member(member_id, owner_user_id="user-1", avatar="avatars/agent-1.png")

    monkeypatch.setattr(entities_router, "_get_owned_avatar_member_or_404", fake_helper)

    fake_repo = SimpleNamespace(
        get_by_id=lambda _member_id: (_ for _ in ()).throw(AssertionError("route should use helper, not repo lookup directly")),
        update=lambda member_id, **fields: seen.append(("update", (member_id, fields))),
    )

    result = await entities_router.delete_avatar(
        "agent-1",
        current_user_id="user-1",
        app=SimpleNamespace(state=SimpleNamespace(member_repo=fake_repo)),
    )

    assert result == {"status": "ok"}
    assert seen == [
        ("helper", ("agent-1", "user-1")),
        ("update", ("agent-1", {"avatar": None, "updated_at": pytest.approx(seen[1][1][1]["updated_at"], rel=0, abs=5)})),
    ]
    assert not avatar_path.exists()


@pytest.mark.asyncio
async def test_upload_avatar_route_uses_auth_shell(monkeypatch: pytest.MonkeyPatch):
    seen: list[tuple[str, object]] = []

    def fake_helper(member_id: str, current_user_id: str, member_repo):
        seen.append(("helper", (member_id, current_user_id)))
        return _member(member_id, owner_user_id="user-1")

    monkeypatch.setattr(entities_router, "_get_owned_avatar_member_or_404", fake_helper)
    monkeypatch.setattr(entities_router, "process_and_save_avatar", lambda data, member_id: seen.append(("save", (data, member_id))) or f"avatars/{member_id}.png")

    fake_repo = SimpleNamespace(
        get_by_id=lambda _member_id: (_ for _ in ()).throw(AssertionError("route should use helper, not repo lookup directly")),
        update=lambda member_id, **fields: seen.append(("update", (member_id, fields))),
    )

    result = await entities_router.upload_avatar(
        "agent-1",
        _FakeUploadFile(b"png-bytes", content_type="image/png"),
        current_user_id="user-1",
        app=SimpleNamespace(state=SimpleNamespace(member_repo=fake_repo)),
    )

    assert result == {"status": "ok", "avatar": "avatars/agent-1.png"}
    assert seen[0] == ("helper", ("agent-1", "user-1"))
    assert seen[1] == ("save", (b"png-bytes", "agent-1"))
    assert seen[2][0] == "update"
    assert seen[2][1][0] == "agent-1"
    assert seen[2][1][1]["avatar"] == "avatars/agent-1.png"
