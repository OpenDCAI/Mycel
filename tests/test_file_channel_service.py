from __future__ import annotations

from pathlib import Path

import pytest

from storage.runtime import build_storage_container


@pytest.fixture()
def _patch_services(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect both file_channel_service and workspace_service to a temp DB."""
    import backend.web.services.file_channel_service as fc_svc
    import backend.web.services.workspace_service as ws_svc
    import backend.web.utils.helpers as helpers

    db_path = tmp_path / "leon.db"
    root_path = tmp_path / "thread_files"
    monkeypatch.setattr(fc_svc, "THREAD_FILES_ROOT", root_path)

    container = build_storage_container(main_db_path=db_path)
    monkeypatch.setattr(helpers, "_cached_container", container)
    monkeypatch.setattr(helpers, "_cached_container_db_path", db_path)

    return tmp_path, root_path


def test_ensure_thread_file_channel_creates_paths_and_row(_patch_services) -> None:
    import backend.web.services.file_channel_service as svc

    payload = svc.ensure_thread_file_channel("thread-1")
    assert payload["thread_id"] == "thread-1"
    assert Path(payload["files_path"]).is_dir()

    rows = svc.list_thread_file_transfers(thread_id="thread-1", limit=10)
    assert rows == []


def test_upload_and_download_record_transfers(_patch_services) -> None:
    import backend.web.services.file_channel_service as svc

    svc.ensure_thread_file_channel("thread-2")

    uploaded = svc.save_uploaded_file(
        thread_id="thread-2",
        relative_path="subdir/sample.txt",
        content=b"hello-upload",
    )
    assert uploaded["size_bytes"] == 12
    assert Path(uploaded["absolute_path"]).read_bytes() == b"hello-upload"

    target = svc.resolve_download_file(
        thread_id="thread-2",
        relative_path="subdir/sample.txt",
    )
    assert target.name == "sample.txt"

    files = svc.list_channel_files(thread_id="thread-2")
    assert [row["relative_path"] for row in files] == ["subdir/sample.txt"]

    transfers = svc.list_thread_file_transfers(thread_id="thread-2", limit=10)
    assert [row["direction"] for row in transfers] == ["download", "upload"]


def test_cleanup_removes_disk_and_db_records(_patch_services) -> None:
    _, root_path = _patch_services
    import backend.web.services.file_channel_service as svc

    svc.ensure_thread_file_channel("thread-cleanup")
    svc.save_uploaded_file(thread_id="thread-cleanup", relative_path="f.txt", content=b"data")
    assert (root_path / "thread-cleanup").is_dir()

    svc.cleanup_thread_file_channel("thread-cleanup")

    assert not (root_path / "thread-cleanup").exists()
    rows = svc.list_thread_file_transfers(thread_id="thread-cleanup", limit=10)
    assert rows == []


def test_upload_rejects_path_escape(_patch_services) -> None:
    import backend.web.services.file_channel_service as svc

    svc.ensure_thread_file_channel("thread-3")

    with pytest.raises(ValueError):
        svc.save_uploaded_file(
            thread_id="thread-3",
            relative_path="../escape.txt",
            content=b"x",
        )


def test_workspace_shared_across_threads(_patch_services) -> None:
    """Two threads sharing a workspace see each other's files in the same channel dir."""
    _, root_path = _patch_services
    import backend.web.services.file_channel_service as svc
    import backend.web.services.workspace_service as ws_svc

    host_path = root_path.parent / "shared_workspace"
    host_path.mkdir()

    ws = ws_svc.create_workspace(str(host_path), name="shared")
    wid = ws["workspace_id"]

    # Thread A uploads a file
    svc.ensure_thread_file_channel("thread-a", workspace_id=wid)
    svc.save_uploaded_file(thread_id="thread-a", relative_path="shared.txt", content=b"data")

    # Thread B shares the same workspace — should see the file
    svc.ensure_thread_file_channel("thread-b", workspace_id=wid)
    files = svc.list_channel_files(thread_id="thread-b")
    assert len(files) == 1 and files[0]["relative_path"] == "shared.txt"

    # Cleanup thread-a must NOT delete host_path
    svc.cleanup_thread_file_channel("thread-a")
    assert host_path.exists(), "workspace host_path wrongly deleted by cleanup"
    assert (host_path / "shared.txt").exists(), "shared file wrongly deleted"
