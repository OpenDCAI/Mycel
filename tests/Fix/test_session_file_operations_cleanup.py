import sqlite3

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
