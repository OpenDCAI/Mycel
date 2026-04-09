from __future__ import annotations

import pytest

from storage import runtime as storage_runtime
from storage.providers.supabase.chat_session_repo import SupabaseChatSessionRepo
from storage.providers.supabase.lease_repo import SupabaseLeaseRepo
from storage.providers.supabase.panel_task_repo import SupabasePanelTaskRepo
from storage.providers.supabase.sandbox_monitor_repo import SupabaseSandboxMonitorRepo
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


@pytest.mark.parametrize(
    ("builder_name", "repo_cls"),
    [
        ("build_lease_repo", SupabaseLeaseRepo),
        ("build_terminal_repo", SupabaseTerminalRepo),
        ("build_chat_session_repo", SupabaseChatSessionRepo),
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
