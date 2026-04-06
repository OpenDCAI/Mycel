from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.routers import settings as settings_router


def test_resolve_workspace_path_or_400_returns_normalized_path(tmp_path: Path):
    result = settings_router._resolve_workspace_path_or_400(
        str(tmp_path),
        missing_detail="missing",
        not_dir_detail="not-dir",
    )

    assert result == str(tmp_path.resolve())


def test_resolve_workspace_path_or_400_uses_route_specific_messages(tmp_path: Path):
    missing = tmp_path / "missing"
    file_path = tmp_path / "note.txt"
    file_path.write_text("x", encoding="utf-8")

    with pytest.raises(HTTPException) as missing_exc:
        settings_router._resolve_workspace_path_or_400(
            str(missing),
            missing_detail="Workspace path does not exist",
            not_dir_detail="Workspace path is not a directory",
        )

    with pytest.raises(HTTPException) as file_exc:
        settings_router._resolve_workspace_path_or_400(
            str(file_path),
            missing_detail="Invalid workspace path",
            not_dir_detail="Invalid workspace path",
        )

    assert missing_exc.value.status_code == 400
    assert missing_exc.value.detail == "Workspace path does not exist"
    assert file_exc.value.status_code == 400
    assert file_exc.value.detail == "Invalid workspace path"


def test_remember_recent_workspace_dedupes_and_truncates():
    settings = settings_router.WorkspaceSettings(
        default_workspace="/keep-default",
        recent_workspaces=["/a", "/b", "/c", "/d", "/e"],
    )

    settings_router._remember_recent_workspace(settings, "/c")
    settings_router._remember_recent_workspace(settings, "/z")

    assert settings.default_workspace == "/keep-default"
    assert settings.recent_workspaces == ["/z", "/c", "/a", "/b", "/d"]


@pytest.mark.asyncio
async def test_set_default_workspace_uses_helpers(monkeypatch: pytest.MonkeyPatch):
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(user_settings_repo=None)))
    settings = settings_router.WorkspaceSettings(default_workspace=None, recent_workspaces=["/old"])
    seen: list[tuple[str, object]] = []

    def fake_resolve(workspace: str, *, missing_detail: str, not_dir_detail: str) -> str:
        seen.append(("resolve", (workspace, missing_detail, not_dir_detail)))
        return "/resolved"

    def fake_load_settings():
        seen.append(("load", None))
        return settings

    def fake_remember(current_settings, workspace_str: str) -> None:
        seen.append(("remember", (current_settings, workspace_str)))
        current_settings.recent_workspaces = [workspace_str, "/old"]

    def fake_save_settings(current_settings) -> None:
        seen.append(("save", current_settings))

    monkeypatch.setattr(settings_router, "_resolve_workspace_path_or_400", fake_resolve)
    monkeypatch.setattr(settings_router, "load_settings", fake_load_settings)
    monkeypatch.setattr(settings_router, "_remember_recent_workspace", fake_remember)
    monkeypatch.setattr(settings_router, "save_settings", fake_save_settings)

    result = await settings_router.set_default_workspace(
        settings_router.WorkspaceRequest(workspace="~/project"),
        req=req,
        user_id="user-1",
    )

    assert result == {"success": True, "workspace": "/resolved"}
    assert settings.default_workspace == "/resolved"
    assert settings.recent_workspaces == ["/resolved", "/old"]
    assert seen == [
        ("resolve", ("~/project", "Workspace path does not exist", "Workspace path is not a directory")),
        ("load", None),
        ("remember", (settings, "/resolved")),
        ("save", settings),
    ]


@pytest.mark.asyncio
async def test_add_recent_workspace_uses_helpers_without_changing_default(monkeypatch: pytest.MonkeyPatch):
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(user_settings_repo=None)))
    settings = settings_router.WorkspaceSettings(default_workspace="/keep-default", recent_workspaces=["/old"])
    seen: list[tuple[str, object]] = []

    def fake_resolve(workspace: str, *, missing_detail: str, not_dir_detail: str) -> str:
        seen.append(("resolve", (workspace, missing_detail, not_dir_detail)))
        return "/recent-only"

    def fake_load_settings():
        seen.append(("load", None))
        return settings

    def fake_remember(current_settings, workspace_str: str) -> None:
        seen.append(("remember", (current_settings, workspace_str)))
        current_settings.recent_workspaces = [workspace_str, "/old"]

    def fake_save_settings(current_settings) -> None:
        seen.append(("save", current_settings))

    monkeypatch.setattr(settings_router, "_resolve_workspace_path_or_400", fake_resolve)
    monkeypatch.setattr(settings_router, "load_settings", fake_load_settings)
    monkeypatch.setattr(settings_router, "_remember_recent_workspace", fake_remember)
    monkeypatch.setattr(settings_router, "save_settings", fake_save_settings)

    result = await settings_router.add_recent_workspace(
        settings_router.WorkspaceRequest(workspace="~/recent"),
        req=req,
        user_id="user-1",
    )

    assert result == {"success": True}
    assert settings.default_workspace == "/keep-default"
    assert settings.recent_workspaces == ["/recent-only", "/old"]
    assert seen == [
        ("resolve", ("~/recent", "Invalid workspace path", "Invalid workspace path")),
        ("load", None),
        ("remember", (settings, "/recent-only")),
        ("save", settings),
    ]
