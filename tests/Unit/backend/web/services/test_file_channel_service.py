from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.web.services import file_channel_service


class _ThreadRepo:
    def get_by_id(self, thread_id: str):
        assert thread_id == "thread-1"
        return {"id": thread_id, "current_workspace_id": "workspace-1"}


class _WorkspaceRepo:
    def get_by_id(self, workspace_id: str):
        assert workspace_id == "workspace-1"
        return SimpleNamespace(id=workspace_id, workspace_path="/workspace/root")


class _Container:
    def thread_repo(self) -> _ThreadRepo:
        return _ThreadRepo()

    def workspace_repo(self) -> _WorkspaceRepo:
        return _WorkspaceRepo()


def test_get_file_channel_binding_uses_workspace_owned_local_channel_root(monkeypatch):
    monkeypatch.setattr(file_channel_service, "_get_container", lambda: _Container())
    monkeypatch.setattr(file_channel_service, "user_home_path", lambda *parts: Path("/tmp/leon-home").joinpath(*parts))
    expected_root = Path("/tmp/leon-home/file_channels/workspace-1").resolve()

    binding = file_channel_service.get_file_channel_binding("thread-1")

    assert binding.thread_id == "thread-1"
    assert binding.workspace_id == "workspace-1"
    assert binding.workspace_path == "/workspace/root"
    assert binding.local_staging_root == expected_root


def test_get_file_channel_source_uses_workspace_owned_local_channel_root(monkeypatch):
    monkeypatch.setattr(file_channel_service, "_get_container", lambda: _Container())
    monkeypatch.setattr(file_channel_service, "user_home_path", lambda *parts: Path("/tmp/leon-home").joinpath(*parts))
    expected_root = Path("/tmp/leon-home/file_channels/workspace-1").resolve()

    source = file_channel_service.get_file_channel_source("thread-1")

    assert source.host_path == expected_root


def test_save_file_does_not_touch_chat_session_activity(monkeypatch):
    class Source:
        def save_file(self, relative_path: str, content: bytes) -> dict:
            assert relative_path == "note.txt"
            assert content == b"hello"
            return {"path": "note.txt", "size": 5}

    monkeypatch.setattr(file_channel_service, "get_file_channel_source", lambda _thread_id: Source())
    monkeypatch.setattr(
        file_channel_service,
        "make_chat_session_repo",
        lambda: (_ for _ in ()).throw(AssertionError("file channel save should not touch chat sessions")),
        raising=False,
    )

    result = file_channel_service.save_file(thread_id="thread-1", relative_path="note.txt", content=b"hello")

    assert result == {"path": "note.txt", "size": 5, "thread_id": "thread-1"}
