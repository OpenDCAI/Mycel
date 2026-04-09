import sqlite3
from pathlib import Path

from storage.providers.sqlite.file_operation_repo import SQLiteFileOperationRepo
from storage.session_manager import SessionManager


def test_session_delete_thread_cleans_file_operations(tmp_path):
    session_dir = tmp_path / ".leon"
    session_dir.mkdir(parents=True)
    db_path = session_dir / "leon.db"

    repo = SQLiteFileOperationRepo(db_path)
    repo.record("t-clean", "cp-1", "write", "/tmp/a.txt", None, "x")
    repo.record("t-other", "cp-2", "write", "/tmp/b.txt", None, "y")

    manager = SessionManager(session_dir=session_dir)
    manager.save_session("t-clean")

    ok = manager.delete_thread("t-clean")
    assert ok is True

    with sqlite3.connect(str(db_path)) as conn:
        n_clean = conn.execute(
            "SELECT COUNT(*) FROM file_operations WHERE thread_id = ?",
            ("t-clean",),
        ).fetchone()[0]
        n_other = conn.execute(
            "SELECT COUNT(*) FROM file_operations WHERE thread_id = ?",
            ("t-other",),
        ).fetchone()[0]

    assert n_clean == 0
    assert n_other == 1


def test_session_delete_thread_uses_runtime_container_under_supabase(monkeypatch, tmp_path):
    deleted: list[tuple[str, str]] = []
    closed: list[str] = []

    class _FakeCheckpointRepo:
        def delete_thread_data(self, thread_id: str) -> None:
            deleted.append(("checkpoint", thread_id))

        def close(self) -> None:
            closed.append("checkpoint")

    class _FakeFileOperationRepo:
        def delete_thread_operations(self, thread_id: str) -> None:
            deleted.append(("file_operation", thread_id))

        def close(self) -> None:
            closed.append("file_operation")

    class _FakeContainer:
        def checkpoint_repo(self):
            return _FakeCheckpointRepo()

        def file_operation_repo(self):
            return _FakeFileOperationRepo()

    session_dir = tmp_path / ".leon"
    session_dir.mkdir(parents=True)
    manager = SessionManager(session_dir=session_dir)
    manager.save_session("t-supabase")

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr("storage.session_manager.build_storage_container", lambda **kwargs: _FakeContainer())

    ok = manager.delete_thread("t-supabase")

    assert ok is True
    assert deleted == [("checkpoint", "t-supabase"), ("file_operation", "t-supabase")]
    assert closed == ["checkpoint", "file_operation"]
    assert manager.db_path == Path(session_dir / "leon.db")
