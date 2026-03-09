from __future__ import annotations

from pathlib import Path

import pytest

from storage.runtime import build_storage_container


@pytest.fixture()
def _patch_services(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect workspace_service to a temp DB."""
    import backend.web.services.workspace_service as ws_svc
    import backend.web.utils.helpers as helpers

    db_path = tmp_path / "leon.db"
    root_path = tmp_path / "thread_files"
    monkeypatch.setattr(ws_svc, "THREAD_FILES_ROOT", root_path)

    # @@@patch-db-path - must also patch DB_PATH so _get_container() doesn't rebuild with production path.
    monkeypatch.setattr(helpers, "DB_PATH", db_path)
    container = build_storage_container(main_db_path=db_path)
    monkeypatch.setattr(helpers, "_cached_container", container)
    monkeypatch.setattr(helpers, "_cached_container_db_path", db_path)

    return tmp_path, root_path


def _save_thread_config(thread_id: str, workspace_id: str | None = None):
    """Helper: create a thread_config row so _get_files_dir can resolve workspace_id."""
    from backend.web.utils.helpers import _get_container

    repo = _get_container().thread_config_repo()
    try:
        repo.save_metadata(thread_id, "local", None)
        if workspace_id:
            repo.update_fields(thread_id, workspace_id=workspace_id)
    finally:
        repo.close()


def test_ensure_thread_files_creates_dir(_patch_services) -> None:
    import backend.web.services.workspace_service as svc

    payload = svc.ensure_thread_files("thread-1")
    assert payload["thread_id"] == "thread-1"
    assert Path(payload["files_path"]).is_dir()


def test_upload_and_download(_patch_services) -> None:
    import backend.web.services.workspace_service as svc

    _save_thread_config("thread-2")
    svc.ensure_thread_files("thread-2")

    uploaded = svc.save_file(
        thread_id="thread-2",
        relative_path="subdir/sample.txt",
        content=b"hello-upload",
    )
    assert uploaded["size_bytes"] == 12
    assert Path(uploaded["absolute_path"]).read_bytes() == b"hello-upload"

    target = svc.resolve_file(
        thread_id="thread-2",
        relative_path="subdir/sample.txt",
    )
    assert target.name == "sample.txt"

    files = svc.list_files(thread_id="thread-2")
    assert [row["relative_path"] for row in files] == ["subdir/sample.txt"]


def test_cleanup_removes_disk(_patch_services) -> None:
    _, root_path = _patch_services
    import backend.web.services.workspace_service as svc

    _save_thread_config("thread-cleanup")
    svc.ensure_thread_files("thread-cleanup")
    svc.save_file(thread_id="thread-cleanup", relative_path="f.txt", content=b"data")
    assert (root_path / "thread-cleanup").is_dir()

    svc.cleanup_thread_files("thread-cleanup")

    assert not (root_path / "thread-cleanup").exists()


def test_upload_rejects_path_escape(_patch_services) -> None:
    import backend.web.services.workspace_service as svc

    _save_thread_config("thread-3")
    svc.ensure_thread_files("thread-3")

    with pytest.raises(ValueError):
        svc.save_file(
            thread_id="thread-3",
            relative_path="../escape.txt",
            content=b"x",
        )


def test_file_channel_workspace_created(_patch_services) -> None:
    """File channel workspace is created automatically."""
    _, root_path = _patch_services
    import backend.web.services.workspace_service as svc

    workspace_id = svc.create_file_channel_workspace("thread-fc")
    ws = svc._get_workspace(workspace_id)

    assert ws is not None
    assert "file-channel" in ws["name"]
    assert str(root_path / "thread-fc" / "files") in ws["host_path"]


def test_workspace_shared_across_threads(_patch_services) -> None:
    """Two threads sharing a workspace see each other's files."""
    _, root_path = _patch_services
    import backend.web.services.workspace_service as svc

    host_path = root_path.parent / "shared_workspace"
    host_path.mkdir()

    ws = svc._create_workspace(str(host_path), name="shared")
    wid = ws["workspace_id"]

    _save_thread_config("thread-a", workspace_id=wid)
    svc.ensure_thread_files("thread-a", workspace_id=wid)
    svc.save_file(thread_id="thread-a", relative_path="shared.txt", content=b"data")

    _save_thread_config("thread-b", workspace_id=wid)
    svc.ensure_thread_files("thread-b", workspace_id=wid)
    files = svc.list_files(thread_id="thread-b")
    assert len(files) == 1 and files[0]["relative_path"] == "shared.txt"

    svc.cleanup_thread_files("thread-a")
    assert host_path.exists(), "workspace host_path wrongly deleted by cleanup"
    assert (host_path / "shared.txt").exists(), "shared file wrongly deleted"
