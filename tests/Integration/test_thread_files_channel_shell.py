from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from backend.web.routers import thread_files as thread_files_router
from backend.web.services import file_channel_service


def test_file_channel_service_no_longer_imports_storage_factory() -> None:
    file_channel_source = inspect.getsource(file_channel_service)

    assert "backend.web.core.storage_factory" not in file_channel_source
    assert "storage.runtime" in file_channel_source
    assert "backend.web.utils.helpers" in file_channel_source
    assert "SQLiteTerminalRepo" not in file_channel_source
    assert "SQLiteLeaseRepo" not in file_channel_source


def test_helpers_no_longer_import_storage_factory() -> None:
    helpers_source = Path("backend/web/utils/helpers.py").read_text(encoding="utf-8")

    assert "backend.web.core.storage_factory" not in helpers_source
    assert "storage.runtime" in helpers_source
    assert "resolve_role_db_path" not in helpers_source
    assert "sandbox.control_plane_repos" in helpers_source


@pytest.mark.asyncio
async def test_call_channel_file_service_maps_value_error_to_400():
    def fake_method(*_args: object, **_kwargs: object):
        raise ValueError("bad path")

    with pytest.raises(HTTPException) as exc_info:
        await thread_files_router._call_channel_file_service(fake_method, thread_id="thread-1")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "bad path"


@pytest.mark.asyncio
async def test_call_channel_file_service_maps_missing_file_to_404():
    def fake_method(*_args: object, **_kwargs: object):
        raise FileNotFoundError("missing.txt")

    with pytest.raises(HTTPException) as exc_info:
        await thread_files_router._call_channel_file_service(
            fake_method,
            thread_id="thread-1",
            missing_status=404,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "missing.txt"


@pytest.mark.asyncio
async def test_download_file_returns_file_response(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    file_path = tmp_path / "notes.txt"
    file_path.write_text("hello", encoding="utf-8")

    async def fake_call(method, *args: object, **kwargs: object):
        return file_path

    monkeypatch.setattr(thread_files_router, "_call_channel_file_service", fake_call)

    response = await thread_files_router.download_file("thread-1", path="notes.txt")

    assert isinstance(response, FileResponse)
    assert response.path == str(file_path)
    assert response.media_type == "application/octet-stream"


@pytest.mark.asyncio
async def test_delete_workspace_file_returns_ok_payload(monkeypatch: pytest.MonkeyPatch):
    async def fake_call(method, *args: object, **kwargs: object):
        return None

    monkeypatch.setattr(thread_files_router, "_call_channel_file_service", fake_call)

    result = await thread_files_router.delete_workspace_file("thread-1", path="notes.txt")

    assert result == {"ok": True, "path": "notes.txt"}


@pytest.mark.asyncio
async def test_list_channel_files_returns_entries_payload(monkeypatch: pytest.MonkeyPatch):
    async def fake_call(method, *args: object, **kwargs: object):
        return [{"path": "notes.txt"}]

    monkeypatch.setattr(thread_files_router, "_call_channel_file_service", fake_call)

    result = await thread_files_router.list_channel_files("thread-1")

    assert result == {"thread_id": "thread-1", "entries": [{"path": "notes.txt"}]}


@pytest.mark.asyncio
async def test_get_sandbox_files_exposes_workspace_binding_alongside_local_staging_root(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        thread_files_router.file_channel_service,
        "get_file_channel_binding",
        lambda thread_id: SimpleNamespace(
            thread_id=thread_id,
            workspace_id="workspace-1",
            workspace_path="/workspace/root",
            local_staging_root=Path("/tmp/channel-root"),
        ),
        raising=False,
    )

    result = await thread_files_router.get_sandbox_files("thread-1")

    assert result == {
        "thread_id": "thread-1",
        "files_path": "/tmp/channel-root",
        "workspace_id": "workspace-1",
        "workspace_path": "/workspace/root",
    }
