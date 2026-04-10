from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.web.routers import entities as entities_router
from backend.web.utils import serializers


class _FakeUploadFile:
    def __init__(self, content: bytes, *, content_type: str) -> None:
        self._content = content
        self.content_type = content_type

    async def read(self) -> bytes:
        return self._content


def _user(user_id: str, *, owner_user_id: str | None = None, avatar: str | None = None):
    return SimpleNamespace(
        id=user_id,
        owner_user_id=owner_user_id,
        avatar=avatar,
    )


def test_avatar_url_uses_local_file_truth_when_db_avatar_is_null(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    avatar_dir = tmp_path / "avatars"
    avatar_dir.mkdir()
    (avatar_dir / "agent-1.png").write_bytes(b"png")
    monkeypatch.setattr(serializers, "avatars_dir", lambda: avatar_dir)

    assert serializers.avatar_url("agent-1", False) == "/api/users/agent-1/avatar"
    assert serializers.avatar_url("agent-2", False) is None


@pytest.mark.asyncio
async def test_delete_avatar_route_uses_auth_shell(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    seen: list[tuple[str, object]] = []
    avatar_dir = tmp_path / "avatars"
    avatar_dir.mkdir()
    avatar_path = avatar_dir / "agent-1.png"
    avatar_path.write_bytes(b"png")
    monkeypatch.setattr(entities_router, "AVATARS_DIR", avatar_dir)

    def fake_helper(user_id: str, current_user_id: str, user_repo):
        seen.append(("helper", (user_id, current_user_id)))
        return _user(user_id, owner_user_id="user-1", avatar="avatars/agent-1.png")

    monkeypatch.setattr(entities_router, "_get_owned_avatar_user_or_404", fake_helper)

    fake_repo = SimpleNamespace(
        get_by_id=lambda _user_id: (_ for _ in ()).throw(AssertionError("route should use helper, not repo lookup directly")),
        update=lambda user_id, **fields: seen.append(("update", (user_id, fields))),
    )

    result = await entities_router.delete_avatar(
        "agent-1",
        current_user_id="user-1",
        app=SimpleNamespace(state=SimpleNamespace(user_repo=fake_repo)),
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

    def fake_helper(user_id: str, current_user_id: str, user_repo):
        seen.append(("helper", (user_id, current_user_id)))
        return _user(user_id, owner_user_id="user-1")

    monkeypatch.setattr(entities_router, "_get_owned_avatar_user_or_404", fake_helper)
    monkeypatch.setattr(
        entities_router,
        "process_and_save_avatar",
        lambda data, user_id: seen.append(("save", (data, user_id))) or f"avatars/{user_id}.png",
    )

    fake_repo = SimpleNamespace(
        get_by_id=lambda _user_id: (_ for _ in ()).throw(AssertionError("route should use helper, not repo lookup directly")),
        update=lambda user_id, **fields: seen.append(("update", (user_id, fields))),
    )

    result = await entities_router.upload_avatar(
        "agent-1",
        _FakeUploadFile(b"png-bytes", content_type="image/png"),
        current_user_id="user-1",
        app=SimpleNamespace(state=SimpleNamespace(user_repo=fake_repo)),
    )

    assert result == {"status": "ok", "avatar": "avatars/agent-1.png"}
    assert seen[0] == ("helper", ("agent-1", "user-1"))
    assert seen[1] == ("save", (b"png-bytes", "agent-1"))
    assert seen[2][0] == "update"
    assert seen[2][1][0] == "agent-1"
    assert "avatar" not in seen[2][1][1]
    assert seen[2][1][1]["updated_at"] == pytest.approx(seen[2][1][1]["updated_at"], rel=0, abs=5)
