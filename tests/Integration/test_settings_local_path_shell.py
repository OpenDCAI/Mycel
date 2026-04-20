from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.web.routers import settings as settings_router


@pytest.mark.asyncio
async def test_browse_filesystem_lists_directory_entries(tmp_path: Path):
    child = tmp_path / "child"
    child.mkdir()

    result = await settings_router.browse_filesystem(path=str(tmp_path), include_files=False)

    assert result == {
        "current_path": str(tmp_path.resolve()),
        "parent_path": str(tmp_path.resolve().parent),
        "items": [{"name": "child", "path": str(child.resolve()), "is_dir": True}],
    }


@pytest.mark.asyncio
async def test_read_local_file_reads_content(tmp_path: Path):
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello world", encoding="utf-8")

    result = await settings_router.read_local_file(path=str(file_path))

    assert result == {"path": str(file_path.resolve()), "content": "hello world", "truncated": False}


@pytest.mark.asyncio
async def test_browse_and_read_keep_route_specific_path_errors(tmp_path: Path):
    missing = tmp_path / "missing"
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello", encoding="utf-8")

    with pytest.raises(HTTPException) as browse_missing_exc:
        await settings_router.browse_filesystem(path=str(missing), include_files=False)

    with pytest.raises(HTTPException) as browse_wrong_type_exc:
        await settings_router.browse_filesystem(path=str(file_path), include_files=False)

    with pytest.raises(HTTPException) as read_missing_exc:
        await settings_router.read_local_file(path=str(missing))

    with pytest.raises(HTTPException) as read_wrong_type_exc:
        await settings_router.read_local_file(path=str(tmp_path))

    assert browse_missing_exc.value.status_code == 404
    assert browse_missing_exc.value.detail == "Path does not exist"
    assert browse_wrong_type_exc.value.status_code == 400
    assert browse_wrong_type_exc.value.detail == "Path is not a directory"
    assert read_missing_exc.value.status_code == 404
    assert read_missing_exc.value.detail == "File not found"
    assert read_wrong_type_exc.value.status_code == 400
    assert read_wrong_type_exc.value.detail == "Path is a directory"


@pytest.mark.asyncio
async def test_browse_filesystem_reports_permission_denied(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    def _raise_permission_denied(_path: Path):
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "iterdir", _raise_permission_denied)

    with pytest.raises(HTTPException) as exc:
        await settings_router.browse_filesystem(path=str(tmp_path), include_files=False)

    assert exc.value.status_code == 403
    assert exc.value.detail == "Permission denied"
