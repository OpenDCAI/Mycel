from __future__ import annotations

import pytest

from storage import runtime as storage_runtime
from storage.providers.sqlite.sandbox_monitor_repo import SQLiteSandboxMonitorRepo
from storage.providers.supabase.chat_session_repo import SupabaseChatSessionRepo
from storage.providers.supabase.lease_repo import SupabaseLeaseRepo
from storage.providers.supabase.panel_task_repo import SupabasePanelTaskRepo
from storage.providers.supabase.provider_event_repo import SupabaseProviderEventRepo
from storage.providers.supabase.queue_repo import SupabaseQueueRepo
from storage.providers.supabase.sandbox_monitor_repo import SupabaseSandboxMonitorRepo
from storage.providers.supabase.summary_repo import SupabaseSummaryRepo
from storage.providers.supabase.terminal_repo import SupabaseTerminalRepo
from tests.fakes.supabase import FakeSupabaseClient


def _build_fake_supabase_client() -> FakeSupabaseClient:
    return FakeSupabaseClient(tables={})


def test_build_sandbox_monitor_repo_uses_runtime_supabase_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = storage_runtime.build_sandbox_monitor_repo(
        supabase_client_factory="tests.Unit.storage.test_runtime_builder_contract:_build_fake_supabase_client",
    )
    try:
        assert isinstance(repo, SupabaseSandboxMonitorRepo)
    finally:
        repo.close()


def test_build_sandbox_monitor_repo_requires_runtime_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)
    monkeypatch.setattr(
        "backend.web.core.supabase_factory.create_supabase_client",
        lambda: (_ for _ in ()).throw(RuntimeError("missing runtime config")),
    )

    with pytest.raises(RuntimeError, match="missing runtime config"):
        storage_runtime.build_sandbox_monitor_repo()


def test_build_runtime_health_monitor_repo_uses_sqlite_under_explicit_sqlite(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "sqlite")

    repo = storage_runtime.build_runtime_health_monitor_repo(db_path=tmp_path / "sandbox.db")
    try:
        assert isinstance(repo, SQLiteSandboxMonitorRepo)
    finally:
        repo.close()


@pytest.mark.parametrize(
    ("builder_name", "repo_cls"),
    [
        ("build_lease_repo", SupabaseLeaseRepo),
        ("build_terminal_repo", SupabaseTerminalRepo),
        ("build_chat_session_repo", SupabaseChatSessionRepo),
        ("build_provider_event_repo", SupabaseProviderEventRepo),
        ("build_queue_repo", SupabaseQueueRepo),
        ("build_summary_repo", SupabaseSummaryRepo),
    ],
)
def test_runtime_repo_builders_use_supabase_factory(
    monkeypatch: pytest.MonkeyPatch,
    builder_name: str,
    repo_cls: type,
) -> None:
    monkeypatch.setenv(
        "LEON_SUPABASE_CLIENT_FACTORY",
        "tests.Unit.storage.test_runtime_builder_contract:_build_fake_supabase_client",
    )

    repo = getattr(storage_runtime, builder_name)()
    try:
        assert isinstance(repo, repo_cls)
    finally:
        repo.close()


def test_build_panel_task_repo_uses_public_supabase_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.web.core.supabase_factory.create_public_supabase_client",
        lambda: _build_fake_supabase_client(),
    )

    repo = storage_runtime.build_panel_task_repo(
        supabase_client=_build_fake_supabase_client(),
    )
    try:
        assert isinstance(repo, SupabasePanelTaskRepo)
    finally:
        repo.close()


def test_build_storage_container_preserves_explicit_public_client(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakePanelTaskRepo:
        def __init__(self, client: object) -> None:
            captured["client"] = client

        def close(self) -> None:
            return None

    runtime_client = _build_fake_supabase_client()
    public_client = _build_fake_supabase_client()
    monkeypatch.setattr(
        "storage.providers.supabase.panel_task_repo.SupabasePanelTaskRepo",
        _FakePanelTaskRepo,
    )

    repo = storage_runtime.build_storage_container(
        supabase_client=runtime_client,
        public_supabase_client=public_client,
    ).panel_task_repo()
    try:
        assert isinstance(repo, _FakePanelTaskRepo)
        assert captured["client"] is public_client
    finally:
        repo.close()
