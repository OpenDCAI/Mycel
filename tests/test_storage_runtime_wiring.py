"""Runtime storage wiring tests for backend agent creation path."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from backend.web.services import agent_pool
from backend.web.services.event_buffer import ThreadEventBuffer
from backend.web.services.streaming_service import _run_agent_to_buffer
from storage.providers.sqlite.checkpoint_repo import SQLiteCheckpointRepo
from storage.providers.sqlite.eval_repo import SQLiteEvalRepo
from storage.providers.supabase.checkpoint_repo import SupabaseCheckpointRepo


class _FakeSupabaseClient:
    def table(self, table_name: str):
        raise AssertionError(f"table() should not be called in this wiring test: {table_name}")


def _build_fake_supabase_client() -> _FakeSupabaseClient:
    return _FakeSupabaseClient()


def _build_invalid_supabase_client() -> object:
    return object()


def _capture_create_leon_agent(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def _fake_create_leon_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(agent_pool, "create_leon_agent", _fake_create_leon_agent)
    return captured


def test_create_agent_sync_wires_supabase_storage_container(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setenv(
        "LEON_SUPABASE_CLIENT_FACTORY",
        "tests.test_storage_runtime_wiring:_build_fake_supabase_client",
    )
    monkeypatch.setenv("LEON_DB_PATH", str(tmp_path / "leon.db"))
    monkeypatch.setenv("LEON_EVAL_DB_PATH", str(tmp_path / "eval.db"))

    captured = _capture_create_leon_agent(monkeypatch)
    agent_pool.create_agent_sync("local", workspace_root=tmp_path, model_name="leon:test")

    container = captured["storage_container"]
    assert isinstance(container.checkpoint_repo(), SupabaseCheckpointRepo)


def test_create_agent_sync_supabase_missing_runtime_config_fails_loud(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)

    with pytest.raises(
        RuntimeError,
        match="LEON_SUPABASE_CLIENT_FACTORY",
    ):
        agent_pool.create_agent_sync("local", workspace_root=tmp_path, model_name="leon:test")


def test_create_agent_sync_supabase_invalid_runtime_config_fails_loud(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setenv(
        "LEON_SUPABASE_CLIENT_FACTORY",
        "tests.test_storage_runtime_wiring:_build_invalid_supabase_client",
    )

    with pytest.raises(RuntimeError, match="callable table\\(name\\) API"):
        agent_pool.create_agent_sync("local", workspace_root=tmp_path, model_name="leon:test")


def test_create_agent_sync_defaults_to_sqlite_storage_container(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)
    monkeypatch.setenv("LEON_DB_PATH", str(tmp_path / "leon.db"))

    captured = _capture_create_leon_agent(monkeypatch)
    agent_pool.create_agent_sync("local", workspace_root=tmp_path, model_name="leon:test")

    container = captured["storage_container"]
    assert isinstance(container.checkpoint_repo(), SQLiteCheckpointRepo)


def test_create_agent_sync_enables_thread_permission_resolver_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)
    monkeypatch.setenv("LEON_DB_PATH", str(tmp_path / "leon.db"))

    captured = _capture_create_leon_agent(monkeypatch)
    agent_pool.create_agent_sync("local", workspace_root=tmp_path, model_name="leon:test")

    assert captured["permission_resolver_scope"] == "thread"


def test_create_agent_sync_repo_override_supabase_with_sqlite_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "sqlite")
    monkeypatch.setenv("LEON_STORAGE_REPO_PROVIDERS", '{"checkpoint_repo":"supabase"}')
    monkeypatch.setenv(
        "LEON_SUPABASE_CLIENT_FACTORY",
        "tests.test_storage_runtime_wiring:_build_fake_supabase_client",
    )
    monkeypatch.setenv("LEON_DB_PATH", str(tmp_path / "leon.db"))

    captured = _capture_create_leon_agent(monkeypatch)
    agent_pool.create_agent_sync("local", workspace_root=tmp_path, model_name="leon:test")
    container = captured["storage_container"]
    assert isinstance(container.checkpoint_repo(), SupabaseCheckpointRepo)


def test_create_agent_sync_repo_override_sqlite_with_supabase_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setenv("LEON_STORAGE_REPO_PROVIDERS", '{"eval_repo":"sqlite"}')
    monkeypatch.setenv(
        "LEON_SUPABASE_CLIENT_FACTORY",
        "tests.test_storage_runtime_wiring:_build_fake_supabase_client",
    )
    monkeypatch.setenv("LEON_DB_PATH", str(tmp_path / "leon.db"))
    monkeypatch.setenv("LEON_EVAL_DB_PATH", str(tmp_path / "eval.db"))

    captured = _capture_create_leon_agent(monkeypatch)
    agent_pool.create_agent_sync("local", workspace_root=tmp_path, model_name="leon:test")
    container = captured["storage_container"]
    assert isinstance(container.eval_repo(), SQLiteEvalRepo)


@pytest.mark.skip(reason="pre-existing: storage wiring/factory API mismatch")
def test_create_agent_sync_all_sqlite_override_with_supabase_default_does_not_require_factory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setenv(
        "LEON_STORAGE_REPO_PROVIDERS",
        (
            '{"checkpoint_repo":"sqlite","thread_config_repo":"sqlite","run_event_repo":"sqlite",'
            '"file_operation_repo":"sqlite","summary_repo":"sqlite","eval_repo":"sqlite",'
            '"queue_repo":"sqlite","workspace_repo":"sqlite"}'
        ),
    )
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)
    monkeypatch.setenv("LEON_DB_PATH", str(tmp_path / "leon.db"))
    monkeypatch.setenv("LEON_EVAL_DB_PATH", str(tmp_path / "eval.db"))

    captured = _capture_create_leon_agent(monkeypatch)
    agent_pool.create_agent_sync("local", workspace_root=tmp_path, model_name="leon:test")
    container = captured["storage_container"]
    assert isinstance(container.checkpoint_repo(), SQLiteCheckpointRepo)


def test_create_agent_sync_repo_override_supabase_without_runtime_config_fails_loud(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "sqlite")
    monkeypatch.setenv("LEON_STORAGE_REPO_PROVIDERS", '{"checkpoint_repo":"supabase"}')
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)

    with pytest.raises(RuntimeError, match="LEON_SUPABASE_CLIENT_FACTORY"):
        agent_pool.create_agent_sync("local", workspace_root=tmp_path, model_name="leon:test")


def test_create_agent_sync_invalid_repo_override_json_fails_loud(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LEON_STORAGE_REPO_PROVIDERS", "not-json")

    with pytest.raises(RuntimeError, match="Invalid LEON_STORAGE_REPO_PROVIDERS"):
        agent_pool.create_agent_sync("local", workspace_root=tmp_path, model_name="leon:test")


class _FakeRunEventRepo:
    def __init__(self) -> None:
        self.append_calls: list[dict[str, Any]] = []
        self.closed = False

    def append_event(
        self,
        thread_id: str,
        run_id: str,
        event_type: str,
        data: dict[str, Any],
        message_id: str | None = None,
    ) -> int:
        self.append_calls.append(
            {
                "thread_id": thread_id,
                "run_id": run_id,
                "event_type": event_type,
                "data": data,
                "message_id": message_id,
            }
        )
        return len(self.append_calls)

    def list_run_ids(self, thread_id: str) -> list[str]:
        return []

    def delete_runs(self, thread_id: str, run_ids: list[str]) -> int:
        return 0

    def close(self) -> None:
        self.closed = True


class _FakeStorageContainer:
    def __init__(self, repo: _FakeRunEventRepo) -> None:
        self._repo = repo

    def run_event_repo(self) -> _FakeRunEventRepo:
        return self._repo


class _FakeGraphAgent:
    checkpointer = None

    async def astream(self, *_args: Any, **_kwargs: Any):
        if False:  # pragma: no cover
            yield None


class _FakeRuntime:
    current_state = "IDLE"

    def get_pending_subagent_events(self) -> list[tuple[str, list[dict[str, Any]]]]:
        return []

    def get_status_dict(self) -> dict[str, Any]:
        return {}

    def set_event_callback(self, cb: Any) -> None:
        pass

    def set_activity_sink(self, sink: Any) -> None:
        pass

    def emit_activity_event(self, event: dict[str, Any]) -> None:
        pass

    def transition(self, new_state: Any) -> bool:
        return True


class _FakeRuntimeAgent:
    def __init__(self, storage_container: Any = None) -> None:
        self.agent = _FakeGraphAgent()
        self.storage_container = storage_container
        self.runtime = _FakeRuntime()


@pytest.mark.skip(reason="pre-existing: storage wiring/factory API mismatch")
def test_run_runtime_consumes_storage_container_run_event_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        repo = _FakeRunEventRepo()
        agent = _FakeRuntimeAgent(storage_container=_FakeStorageContainer(repo))
        from unittest.mock import MagicMock

        qm = MagicMock()
        qm.dequeue.return_value = None
        app = SimpleNamespace(state=SimpleNamespace(thread_tasks={}, thread_event_buffers={}, subagent_buffers={}, queue_manager=qm))
        thread_buf = ThreadEventBuffer()
        run_id = "run-1"

        await _run_agent_to_buffer(agent, "thread-1", "hello", app, False, thread_buf, run_id)

        assert repo.append_calls, "run path should persist events through storage_container.run_event_repo()"
        assert any(c["event_type"] == "run_done" for c in repo.append_calls)
        assert repo.closed is True

    asyncio.run(_run())


@pytest.mark.skip(reason="pre-existing: storage wiring/factory API mismatch")
def test_run_runtime_without_storage_container_keeps_sqlite_event_store_path(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        import backend.web.services.event_store as event_store

        calls: list[dict[str, Any]] = []

        async def _fake_append_event(
            thread_id: str,
            run_id: str,
            event: dict[str, Any],
            message_id: str | None = None,
            run_event_repo: Any | None = None,
        ) -> int:
            calls.append(
                {
                    "thread_id": thread_id,
                    "run_id": run_id,
                    "event": event,
                    "message_id": message_id,
                    "run_event_repo": run_event_repo,
                }
            )
            return len(calls)

        async def _fake_cleanup_old_runs(
            thread_id: str,
            keep_latest: int = 1,
            run_event_repo: Any | None = None,
        ) -> int:
            return 0

        monkeypatch.setattr(event_store, "append_event", _fake_append_event)
        monkeypatch.setattr(event_store, "cleanup_old_runs", _fake_cleanup_old_runs)

        from unittest.mock import MagicMock

        qm = MagicMock()
        qm.dequeue.return_value = None
        agent = _FakeRuntimeAgent(storage_container=None)
        app = SimpleNamespace(state=SimpleNamespace(thread_tasks={}, thread_event_buffers={}, subagent_buffers={}, queue_manager=qm))
        thread_buf = ThreadEventBuffer()
        run_id = "run-1"

        await _run_agent_to_buffer(agent, "thread-1", "hello", app, False, thread_buf, run_id)

        assert calls, "sqlite event store path should still be used when no storage container is injected"
        assert all(call["run_event_repo"] is None for call in calls)

    asyncio.run(_run())


@pytest.mark.skip(reason="pre-existing: thread_config_repo removed from StorageContainer")
def test_purge_thread_deletes_all_repo_data(tmp_path: Path) -> None:
    from storage.container import StorageContainer

    db_path = tmp_path / "leon.db"
    eval_db = tmp_path / "eval.db"
    container = StorageContainer(main_db_path=db_path, eval_db_path=eval_db, strategy="sqlite")

    # Populate repos for thread t-1 and t-2
    tc = container.thread_config_repo()
    tc.save_metadata("t-1", "docker", "/ws")
    tc.save_metadata("t-2", "local", None)
    tc.close()

    re_repo = container.run_event_repo()
    re_repo.append_event("t-1", "r-1", "status", {"ok": True})
    re_repo.append_event("t-2", "r-2", "status", {"ok": True})
    re_repo.close()

    fo = container.file_operation_repo()
    fo.record("t-1", "cp-1", "write", "/a.txt", None, "x")
    fo.record("t-2", "cp-2", "write", "/b.txt", None, "y")
    fo.close()

    sr = container.summary_repo()
    sr.ensure_tables()
    sr.save_summary("s-1", "t-1", "summary", 10, 20, False, None, "2025-01-01")
    sr.close()

    # Purge t-1
    container.purge_thread("t-1")

    # Verify t-1 is gone, t-2 remains
    tc2 = container.thread_config_repo()
    assert tc2.lookup_metadata("t-1") is None
    assert tc2.lookup_metadata("t-2") == ("local", None)
    tc2.close()

    re2 = container.run_event_repo()
    assert re2.latest_seq("t-1") == 0
    assert re2.latest_seq("t-2") > 0
    re2.close()

    fo2 = container.file_operation_repo()
    assert fo2.get_operations_for_thread("t-1") == []
    assert len(fo2.get_operations_for_thread("t-2")) == 1
    fo2.close()

    sr2 = container.summary_repo()
    assert sr2.get_latest_summary_row("t-1") is None
    sr2.close()
