from __future__ import annotations

from pathlib import Path

from core.runtime.middleware.memory.middleware import MemoryMiddleware
from core.runtime.middleware.memory.summary_store import SummaryStore
from core.runtime.middleware.queue.manager import MessageQueueManager
from storage.providers.sqlite.queue_repo import SQLiteQueueRepo
from storage.providers.sqlite.summary_repo import SQLiteSummaryRepo


def test_build_supabase_client_uses_runtime_factory_ref(monkeypatch) -> None:
    from storage import runtime as storage_runtime

    fake_client = object()
    calls: list[str | None] = []

    def _resolve(*, factory_ref=None):
        calls.append(factory_ref)
        return fake_client

    monkeypatch.setattr(storage_runtime, "_resolve_supabase_client", _resolve)

    assert storage_runtime.build_supabase_client(supabase_client_factory="tests.fake:create_client") is fake_client
    assert calls == ["tests.fake:create_client"]


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


def test_message_queue_manager_requires_runtime_repo_or_explicit_db_path(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)
    monkeypatch.delenv("LEON_QUEUE_DB_PATH", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        "core.runtime.middleware.queue.manager.build_queue_repo",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("runtime repo should not be used")),
    )

    try:
        MessageQueueManager()
    except RuntimeError as exc:
        assert "LEON_QUEUE_DB_PATH" in str(exc)
    else:
        raise AssertionError("MessageQueueManager should require an explicit storage source")

    assert not (tmp_path / ".leon").exists()


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


def test_summary_store_requires_runtime_repo_or_explicit_db_path(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        "core.runtime.middleware.memory.summary_store.build_summary_repo",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("runtime repo should not be used")),
    )

    try:
        SummaryStore()
    except RuntimeError as exc:
        assert "SummaryStore requires summary_repo or db_path" in str(exc)
    else:
        raise AssertionError("SummaryStore should require an explicit storage source")

    assert not (tmp_path / ".leon").exists()


def test_summary_store_repo_injection_does_not_select_local_db_path(monkeypatch, tmp_path) -> None:
    fake_repo = _FakeSummaryRepo()
    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    store = SummaryStore(summary_repo=fake_repo)

    assert store._repo is fake_repo
    assert store.db_path is None
    assert not (tmp_path / ".leon").exists()


def test_summary_store_explicit_db_path_keeps_sqlite_under_supabase(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")

    store = SummaryStore(Path(tmp_path / "summary.db"))

    try:
        assert isinstance(store._repo, SQLiteSummaryRepo)
    finally:
        store._repo.close()


def test_summary_store_explicit_db_path_works_without_runtime_config(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    store = SummaryStore(Path(tmp_path / "summary.db"))

    try:
        assert isinstance(store._repo, SQLiteSummaryRepo)
        assert store.db_path == tmp_path / "summary.db"
        assert not (tmp_path / "home" / ".leon").exists()
    finally:
        store._repo.close()


def test_memory_middleware_repo_injection_does_not_pass_default_home_db_path(monkeypatch) -> None:
    captured: dict[str, object] = {}
    fake_repo = _FakeSummaryRepo()

    class _SummaryStoreProbe:
        def __init__(self, db_path=None, summary_repo=None):
            captured["db_path"] = db_path
            captured["summary_repo"] = summary_repo

    monkeypatch.setattr("core.runtime.middleware.memory.middleware.SummaryStore", _SummaryStoreProbe)

    middleware = MemoryMiddleware(summary_repo=fake_repo)

    assert middleware.summary_store is not None
    assert captured["summary_repo"] is fake_repo
    assert captured["db_path"] is None


def test_memory_middleware_without_storage_source_has_no_summary_store(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    middleware = MemoryMiddleware()

    assert middleware.summary_store is None
    assert not (tmp_path / ".leon").exists()
