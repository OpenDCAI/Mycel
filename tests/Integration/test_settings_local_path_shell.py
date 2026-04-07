from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.web.routers import settings as settings_router


def test_resolve_local_path_or_http_returns_resolved_path(tmp_path: Path):
    result = settings_router._resolve_local_path_or_http(
        str(tmp_path),
        missing_detail="missing",
        wrong_type_detail="wrong-type",
        expect_dir=True,
    )

    assert result == tmp_path.resolve()


def test_resolve_local_path_or_http_preserves_route_specific_errors(tmp_path: Path):
    missing = tmp_path / "missing"
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello", encoding="utf-8")

    with pytest.raises(HTTPException) as missing_exc:
        settings_router._resolve_local_path_or_http(
            str(missing),
            missing_detail="Path does not exist",
            wrong_type_detail="Path is not a directory",
            expect_dir=True,
        )

    with pytest.raises(HTTPException) as wrong_type_exc:
        settings_router._resolve_local_path_or_http(
            str(tmp_path),
            missing_detail="File not found",
            wrong_type_detail="Path is a directory",
            expect_dir=False,
        )

    assert missing_exc.value.status_code == 404
    assert missing_exc.value.detail == "Path does not exist"
    assert wrong_type_exc.value.status_code == 400
    assert wrong_type_exc.value.detail == "Path is a directory"


@pytest.mark.asyncio
async def test_browse_filesystem_uses_local_path_helper(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    child = tmp_path / "child"
    child.mkdir()
    seen: list[tuple[str, object]] = []

    def fake_resolve(path: str, *, missing_detail: str, wrong_type_detail: str, expect_dir: bool) -> Path:
        seen.append(("resolve", (path, missing_detail, wrong_type_detail, expect_dir)))
        return tmp_path

    monkeypatch.setattr(settings_router, "_resolve_local_path_or_http", fake_resolve)

    result = await settings_router.browse_filesystem(path="~/workspace", include_files=False)

    assert result["current_path"] == str(tmp_path)
    assert result["parent_path"] == str(tmp_path.parent)
    assert result["items"] == [{"name": "child", "path": str(child), "is_dir": True}]
    assert seen == [("resolve", ("~/workspace", "Path does not exist", "Path is not a directory", True))]


@pytest.mark.asyncio
async def test_read_local_file_uses_local_path_helper(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello world", encoding="utf-8")
    seen: list[tuple[str, object]] = []

    def fake_resolve(path: str, *, missing_detail: str, wrong_type_detail: str, expect_dir: bool) -> Path:
        seen.append(("resolve", (path, missing_detail, wrong_type_detail, expect_dir)))
        return file_path

    monkeypatch.setattr(settings_router, "_resolve_local_path_or_http", fake_resolve)

    result = await settings_router.read_local_file(path="~/note.txt")

    assert result == {"path": str(file_path), "content": "hello world", "truncated": False}
    assert seen == [("resolve", ("~/note.txt", "File not found", "Path is a directory", False))]
