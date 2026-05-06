from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.web.routers import settings as settings_router
from storage.contracts import UserType


@pytest.mark.asyncio
async def test_browse_filesystem_lists_directory_entries(tmp_path: Path):
    child = tmp_path / "child"
    child.mkdir()

    result = await settings_router.browse_filesystem(_capability=None, path=str(tmp_path), include_files=False)

    assert result == {
        "current_path": str(tmp_path.resolve()),
        "parent_path": str(tmp_path.resolve().parent),
        "items": [{"name": "child", "path": str(child.resolve()), "is_dir": True}],
    }


@pytest.mark.asyncio
async def test_read_local_file_reads_content(tmp_path: Path):
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello world", encoding="utf-8")

    result = await settings_router.read_local_file(_capability=None, path=str(file_path))

    assert result == {"path": str(file_path.resolve()), "content": "hello world", "truncated": False}


@pytest.mark.asyncio
async def test_browse_and_read_keep_route_specific_path_errors(tmp_path: Path):
    missing = tmp_path / "missing"
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello", encoding="utf-8")

    with pytest.raises(HTTPException) as browse_missing_exc:
        await settings_router.browse_filesystem(_capability=None, path=str(missing), include_files=False)

    with pytest.raises(HTTPException) as browse_wrong_type_exc:
        await settings_router.browse_filesystem(_capability=None, path=str(file_path), include_files=False)

    with pytest.raises(HTTPException) as read_missing_exc:
        await settings_router.read_local_file(_capability=None, path=str(missing))

    with pytest.raises(HTTPException) as read_wrong_type_exc:
        await settings_router.read_local_file(_capability=None, path=str(tmp_path))

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
        await settings_router.browse_filesystem(_capability=None, path=str(tmp_path), include_files=False)

    assert exc.value.status_code == 403
    assert exc.value.detail == "Permission denied"


def test_external_user_cannot_browse_local_filesystem_over_http() -> None:
    app = FastAPI()
    app.state.auth_runtime_state = SimpleNamespace(
        auth_service=SimpleNamespace(verify_token=lambda token: {"user_id": "external-1"} if token == "tok-external" else None)
    )
    app.state.user_repo = SimpleNamespace(
        get_by_id=lambda user_id: (
            SimpleNamespace(id=user_id, type=UserType.EXTERNAL, display_name="Codex Local") if user_id == "external-1" else None
        )
    )
    app.include_router(settings_router.router)

    with TestClient(app) as client:
        browse_response = client.get("/api/settings/browse", headers={"Authorization": "Bearer tok-external"})
        read_response = client.get("/api/settings/read", headers={"Authorization": "Bearer tok-external"}, params={"path": "/"})

    assert browse_response.status_code == 403
    assert browse_response.json()["detail"] == "Capability required: inspect_resources"
    assert read_response.status_code == 403
    assert read_response.json()["detail"] == "Capability required: inspect_resources"
