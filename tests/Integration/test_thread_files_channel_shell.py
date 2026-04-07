from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from backend.web.routers import thread_files as thread_files_router


@pytest.mark.asyncio
async def test_call_channel_file_service_maps_value_error_to_400():
    def fake_method(*_args: object, **_kwargs: object):
        raise ValueError("bad path")

    with pytest.raises(HTTPException) as exc_info:
        await thread_files_router._call_channel_file_service(fake_method, "thread-1")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "bad path"


@pytest.mark.asyncio
async def test_call_channel_file_service_maps_missing_file_to_404():
    def fake_method(*_args: object, **_kwargs: object):
        raise FileNotFoundError("missing.txt")

    with pytest.raises(HTTPException) as exc_info:
        await thread_files_router._call_channel_file_service(
            fake_method,
            "thread-1",
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
