from __future__ import annotations

from pathlib import Path

import pytest


def test_ensure_thread_file_channel_creates_paths_and_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.web.services.file_channel_service as svc

    db_path = tmp_path / "leon.db"
    root_path = tmp_path / "thread_files"
    monkeypatch.setattr(svc, "DB_PATH", db_path)
    monkeypatch.setattr(svc, "THREAD_FILES_ROOT", root_path)

    payload = svc.ensure_thread_file_channel("thread-1")
    assert payload["thread_id"] == "thread-1"
    assert Path(payload["upload_path"]).is_dir()
    assert Path(payload["download_path"]).is_dir()

    rows = svc.list_thread_file_transfers(thread_id="thread-1", limit=10)
    assert rows == []


def test_upload_and_download_record_transfers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.web.services.file_channel_service as svc

    db_path = tmp_path / "leon.db"
    root_path = tmp_path / "thread_files"
    monkeypatch.setattr(svc, "DB_PATH", db_path)
    monkeypatch.setattr(svc, "THREAD_FILES_ROOT", root_path)

    svc.ensure_thread_file_channel("thread-2")

    uploaded = svc.save_uploaded_file(
        thread_id="thread-2",
        channel="download",
        relative_path="subdir/sample.txt",
        content=b"hello-upload",
    )
    assert uploaded["size_bytes"] == 12
    assert Path(uploaded["absolute_path"]).read_bytes() == b"hello-upload"

    target = svc.resolve_download_file(
        thread_id="thread-2",
        channel="download",
        relative_path="subdir/sample.txt",
    )
    assert target.name == "sample.txt"

    files = svc.list_channel_files(thread_id="thread-2", channel="download")
    assert [row["relative_path"] for row in files] == ["subdir/sample.txt"]

    transfers = svc.list_thread_file_transfers(thread_id="thread-2", limit=10)
    assert [row["direction"] for row in transfers] == ["download", "upload"]


def test_cleanup_removes_disk_and_db_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.web.services.file_channel_service as svc

    db_path = tmp_path / "leon.db"
    root_path = tmp_path / "thread_files"
    monkeypatch.setattr(svc, "DB_PATH", db_path)
    monkeypatch.setattr(svc, "THREAD_FILES_ROOT", root_path)

    svc.ensure_thread_file_channel("thread-cleanup")
    svc.save_uploaded_file(thread_id="thread-cleanup", channel="download", relative_path="f.txt", content=b"data")
    assert (root_path / "thread-cleanup").is_dir()

    svc.cleanup_thread_file_channel("thread-cleanup")

    assert not (root_path / "thread-cleanup").exists()
    rows = svc.list_thread_file_transfers(thread_id="thread-cleanup", limit=10)
    assert rows == []


def test_upload_rejects_path_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.web.services.file_channel_service as svc

    db_path = tmp_path / "leon.db"
    root_path = tmp_path / "thread_files"
    monkeypatch.setattr(svc, "DB_PATH", db_path)
    monkeypatch.setattr(svc, "THREAD_FILES_ROOT", root_path)

    svc.ensure_thread_file_channel("thread-3")

    with pytest.raises(ValueError):
        svc.save_uploaded_file(
            thread_id="thread-3",
            channel="download",
            relative_path="../escape.txt",
            content=b"x",
        )
