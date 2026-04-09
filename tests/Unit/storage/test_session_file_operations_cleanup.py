import sqlite3
from pathlib import Path

from storage.providers.sqlite.file_operation_repo import SQLiteFileOperationRepo
from storage.session_manager import SessionManager


def test_session_delete_thread_cleans_file_operations(monkeypatch, tmp_path):
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "sqlite")
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


def test_session_delete_thread_uses_runtime_repo_builders_under_supabase(monkeypatch, tmp_path):
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

    session_dir = tmp_path / ".leon"
    session_dir.mkdir(parents=True)
    manager = SessionManager(session_dir=session_dir)
    manager.save_session("t-supabase")

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr("storage.session_manager.build_checkpoint_repo", lambda **kwargs: _FakeCheckpointRepo())
    monkeypatch.setattr("storage.session_manager.build_file_operation_repo", lambda **kwargs: _FakeFileOperationRepo())

    ok = manager.delete_thread("t-supabase")

    assert ok is True
    assert deleted == [("checkpoint", "t-supabase"), ("file_operation", "t-supabase")]
    assert closed == ["checkpoint", "file_operation"]
    assert manager.db_path == Path(session_dir / "leon.db")


def test_session_delete_thread_uses_runtime_repo_builders_under_explicit_supabase(monkeypatch, tmp_path):
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

    session_dir = tmp_path / ".leon"
    session_dir.mkdir(parents=True)
    manager = SessionManager(session_dir=session_dir)
    manager.save_session("t-supabase-builders")

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr(
        "storage.session_manager.build_checkpoint_repo",
        lambda **_kwargs: _FakeCheckpointRepo(),
        raising=False,
    )
    monkeypatch.setattr(
        "storage.session_manager.build_file_operation_repo",
        lambda **_kwargs: _FakeFileOperationRepo(),
        raising=False,
    )

    ok = manager.delete_thread("t-supabase-builders")

    assert ok is True
    assert deleted == [("checkpoint", "t-supabase-builders"), ("file_operation", "t-supabase-builders")]
    assert closed == ["checkpoint", "file_operation"]


def test_session_delete_thread_defaults_to_runtime_repo_builders_when_strategy_missing(monkeypatch, tmp_path):
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

    session_dir = tmp_path / ".leon"
    session_dir.mkdir(parents=True)
    manager = SessionManager(session_dir=session_dir)
    manager.save_session("t-default")

    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.setenv("LEON_SUPABASE_CLIENT_FACTORY", "tests.fake:create_client")
    monkeypatch.setattr("storage.session_manager.build_checkpoint_repo", lambda **kwargs: _FakeCheckpointRepo())
    monkeypatch.setattr("storage.session_manager.build_file_operation_repo", lambda **kwargs: _FakeFileOperationRepo())

    ok = manager.delete_thread("t-default")

    assert ok is True
    assert deleted == [("checkpoint", "t-default"), ("file_operation", "t-default")]
    assert closed == ["checkpoint", "file_operation"]


def test_session_delete_thread_keeps_local_db_when_strategy_missing_and_runtime_config_missing(monkeypatch, tmp_path):
    deleted: list[tuple[str, str]] = []
    closed: list[str] = []

    class _FakeCheckpointRepo:
        def __init__(self, *, db_path):
            self.db_path = db_path

        def delete_thread_data(self, thread_id: str) -> None:
            deleted.append(("checkpoint", thread_id))

        def close(self) -> None:
            closed.append("checkpoint")

    class _FakeFileOperationRepo:
        def __init__(self, *, db_path):
            self.db_path = db_path

        def delete_thread_operations(self, thread_id: str) -> None:
            deleted.append(("file_operation", thread_id))

        def close(self) -> None:
            closed.append("file_operation")

    session_dir = tmp_path / ".leon"
    session_dir.mkdir(parents=True)
    manager = SessionManager(session_dir=session_dir)
    manager.save_session("t-local")
    manager.db_path.touch()

    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)
    monkeypatch.setattr("storage.providers.sqlite.checkpoint_repo.SQLiteCheckpointRepo", _FakeCheckpointRepo)
    monkeypatch.setattr("storage.providers.sqlite.file_operation_repo.SQLiteFileOperationRepo", _FakeFileOperationRepo)

    ok = manager.delete_thread("t-local")

    assert ok is True
    assert deleted == [("checkpoint", "t-local"), ("file_operation", "t-local")]
    assert closed == ["checkpoint", "file_operation"]
