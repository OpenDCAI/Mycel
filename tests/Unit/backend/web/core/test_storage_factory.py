from __future__ import annotations

import pytest

from backend.web.core import storage_factory
from storage.providers.sqlite.chat_session_repo import SQLiteChatSessionRepo
from storage.providers.sqlite.lease_repo import SQLiteLeaseRepo
from storage.providers.sqlite.sandbox_monitor_repo import SQLiteSandboxMonitorRepo
from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo
from storage.providers.supabase.chat_session_repo import SupabaseChatSessionRepo
from storage.providers.supabase.lease_repo import SupabaseLeaseRepo
from storage.providers.supabase.sandbox_monitor_repo import SupabaseSandboxMonitorRepo
from storage.providers.supabase.terminal_repo import SupabaseTerminalRepo
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


@pytest.mark.parametrize(
    ("factory_name", "sqlite_cls", "supabase_cls"),
    [
        ("make_lease_repo", SQLiteLeaseRepo, SupabaseLeaseRepo),
        ("make_terminal_repo", SQLiteTerminalRepo, SupabaseTerminalRepo),
        ("make_chat_session_repo", SQLiteChatSessionRepo, SupabaseChatSessionRepo),
    ],
)
def test_repo_factories_default_to_sqlite(
    monkeypatch: pytest.MonkeyPatch,
    factory_name: str,
    sqlite_cls: type,
    supabase_cls: type,
) -> None:
    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)
    storage_factory._supabase_client.cache_clear()

    repo = getattr(storage_factory, factory_name)()
    try:
        assert isinstance(repo, sqlite_cls)
        assert not isinstance(repo, supabase_cls)
    finally:
        repo.close()


@pytest.mark.parametrize(
    ("factory_name", "supabase_cls"),
    [
        ("make_lease_repo", SupabaseLeaseRepo),
        ("make_terminal_repo", SupabaseTerminalRepo),
        ("make_chat_session_repo", SupabaseChatSessionRepo),
    ],
)
def test_repo_factories_use_supabase_for_supabase_strategy(
    monkeypatch: pytest.MonkeyPatch,
    factory_name: str,
    supabase_cls: type,
) -> None:
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setenv(
        "LEON_SUPABASE_CLIENT_FACTORY",
        "tests.Unit.backend.web.core.test_storage_factory:_build_fake_supabase_client",
    )
    storage_factory._supabase_client.cache_clear()

    repo = getattr(storage_factory, factory_name)()
    try:
        assert isinstance(repo, supabase_cls)
    finally:
        repo.close()
