from __future__ import annotations

from pathlib import Path

from core.runtime.middleware.memory.summary_store import SummaryStore
from core.runtime.middleware.queue.manager import MessageQueueManager
from storage.providers.sqlite.queue_repo import SQLiteQueueRepo
from storage.providers.sqlite.summary_repo import SQLiteSummaryRepo


class _FakeQueueRepo:
    def close(self) -> None:
        return None


class _FakeSummaryRepo:
    def ensure_tables(self) -> None:
        return None

    def close(self) -> None:
        return None


def test_message_queue_manager_uses_runtime_repo_under_explicit_supabase(monkeypatch) -> None:
    fake_repo = _FakeQueueRepo()

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr(
        "core.runtime.middleware.queue.manager.build_queue_repo",
        lambda **_kwargs: fake_repo,
    )

    manager = MessageQueueManager()

    assert manager._repo is fake_repo


def test_message_queue_manager_defaults_to_runtime_repo_when_strategy_missing(monkeypatch) -> None:
    fake_repo = _FakeQueueRepo()

    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.setenv("LEON_SUPABASE_CLIENT_FACTORY", "tests.fake:create_client")
    monkeypatch.setattr(
        "core.runtime.middleware.queue.manager.build_queue_repo",
        lambda **_kwargs: fake_repo,
    )

    manager = MessageQueueManager()

    assert manager._repo is fake_repo


def test_message_queue_manager_keeps_sqlite_when_strategy_missing_and_runtime_config_missing(monkeypatch) -> None:
    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)
    monkeypatch.setattr(
        "core.runtime.middleware.queue.manager.build_queue_repo",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("runtime repo should not be used")),
    )

    class _SQLiteQueueRepoStub:
        def __init__(self, db_path=None):
            self.db_path = db_path

        def close(self) -> None:
            return None

    monkeypatch.setattr("storage.providers.sqlite.queue_repo.SQLiteQueueRepo", _SQLiteQueueRepoStub)

    manager = MessageQueueManager()

    assert isinstance(manager._repo, _SQLiteQueueRepoStub)


def test_message_queue_manager_explicit_db_path_keeps_sqlite_under_supabase(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")

    manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))

    try:
        assert isinstance(manager._repo, SQLiteQueueRepo)
    finally:
        manager._repo.close()


def test_summary_store_uses_runtime_repo_under_explicit_supabase(monkeypatch) -> None:
    fake_repo = _FakeSummaryRepo()

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr(
        "core.runtime.middleware.memory.summary_store.build_summary_repo",
        lambda **_kwargs: fake_repo,
    )

    store = SummaryStore()

    assert store._repo is fake_repo


def test_summary_store_defaults_to_runtime_repo_when_strategy_missing(monkeypatch) -> None:
    fake_repo = _FakeSummaryRepo()

    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.setenv("LEON_SUPABASE_CLIENT_FACTORY", "tests.fake:create_client")
    monkeypatch.setattr(
        "core.runtime.middleware.memory.summary_store.build_summary_repo",
        lambda **_kwargs: fake_repo,
    )

    store = SummaryStore()

    assert store._repo is fake_repo


def test_summary_store_keeps_sqlite_when_strategy_missing_and_runtime_config_missing(monkeypatch) -> None:
    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)
    monkeypatch.setattr(
        "core.runtime.middleware.memory.summary_store.build_summary_repo",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("runtime repo should not be used")),
    )

    class _SQLiteSummaryRepoStub:
        def __init__(self, db_path, connect_fn=None):
            self.db_path = db_path

        def ensure_tables(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr("core.runtime.middleware.memory.summary_store.SQLiteSummaryRepo", _SQLiteSummaryRepoStub)

    store = SummaryStore()

    assert isinstance(store._repo, _SQLiteSummaryRepoStub)


def test_summary_store_explicit_db_path_keeps_sqlite_under_supabase(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")

    store = SummaryStore(Path(tmp_path / "summary.db"))

    try:
        assert isinstance(store._repo, SQLiteSummaryRepo)
    finally:
        store._repo.close()
