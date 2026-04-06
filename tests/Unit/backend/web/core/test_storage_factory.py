from __future__ import annotations

import pytest

from backend.web.core import storage_factory
from storage.providers.sqlite.sandbox_monitor_repo import SQLiteSandboxMonitorRepo
from storage.providers.supabase.sandbox_monitor_repo import SupabaseSandboxMonitorRepo
from tests.fakes.supabase import FakeSupabaseClient


def _build_fake_supabase_client() -> FakeSupabaseClient:
    return FakeSupabaseClient(tables={})


def test_make_sandbox_monitor_repo_defaults_to_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)
    storage_factory._supabase_client.cache_clear()

    repo = storage_factory.make_sandbox_monitor_repo()
    try:
        assert isinstance(repo, SQLiteSandboxMonitorRepo)
    finally:
        repo.close()


def test_make_sandbox_monitor_repo_uses_supabase_for_supabase_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setenv(
        "LEON_SUPABASE_CLIENT_FACTORY",
        "tests.Unit.backend.web.core.test_storage_factory:_build_fake_supabase_client",
    )
    storage_factory._supabase_client.cache_clear()

    repo = storage_factory.make_sandbox_monitor_repo()
    try:
        assert isinstance(repo, SupabaseSandboxMonitorRepo)
    finally:
        repo.close()


def test_make_sandbox_monitor_repo_supabase_requires_runtime_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)
    storage_factory._supabase_client.cache_clear()

    with pytest.raises(RuntimeError):
        storage_factory.make_sandbox_monitor_repo()
