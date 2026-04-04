"""Runtime storage wiring tests for backend agent creation path."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.web.services import agent_pool
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
        "tests.Integration.test_storage_runtime_wiring:_build_fake_supabase_client",
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
        "tests.Integration.test_storage_runtime_wiring:_build_invalid_supabase_client",
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
        "tests.Integration.test_storage_runtime_wiring:_build_fake_supabase_client",
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
        "tests.Integration.test_storage_runtime_wiring:_build_fake_supabase_client",
    )
    monkeypatch.setenv("LEON_DB_PATH", str(tmp_path / "leon.db"))
    monkeypatch.setenv("LEON_EVAL_DB_PATH", str(tmp_path / "eval.db"))

    captured = _capture_create_leon_agent(monkeypatch)
    agent_pool.create_agent_sync("local", workspace_root=tmp_path, model_name="leon:test")
    container = captured["storage_container"]
    assert isinstance(container.eval_repo(), SQLiteEvalRepo)


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


