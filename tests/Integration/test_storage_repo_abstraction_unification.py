from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from backend.web.core import lifespan as lifespan_module
from core.agents.registry import AgentRegistry
from core.runtime.registry import ToolRegistry
from core.tools.task.service import TaskService
from sandbox import resource_snapshot as resource_snapshot_module
from sandbox.sync.state import SyncState
from storage import runtime as storage_runtime
from storage.container import StorageContainer


class _FakeSupabaseClient:
    pass


class _FakeRepo:
    def close(self) -> None:
        return None


class _FakeContainer:
    def __init__(self) -> None:
        self.user_repo_value = _FakeRepo()
        self.thread_repo_value = _FakeRepo()
        self.lease_repo_value = _FakeRepo()
        self.terminal_repo_value = _FakeRepo()
        self.chat_session_repo_value = _FakeRepo()
        self.sandbox_volume_repo_value = _FakeRepo()
        self.thread_launch_pref_repo_value = _FakeRepo()
        self.recipe_repo_value = _FakeRepo()
        self.chat_repo_value = _FakeRepo()
        self.invite_code_repo_value = _FakeRepo()
        self.user_settings_repo_value = _FakeRepo()
        self.agent_config_repo_value = _FakeRepo()
        self.contact_repo_value = _FakeRepo()
        self.panel_task_repo_value = _FakeRepo()

    def user_repo(self) -> _FakeRepo:
        return self.user_repo_value

    def thread_repo(self) -> _FakeRepo:
        return self.thread_repo_value

    def lease_repo(self) -> _FakeRepo:
        return self.lease_repo_value

    def terminal_repo(self) -> _FakeRepo:
        return self.terminal_repo_value

    def chat_session_repo(self) -> _FakeRepo:
        return self.chat_session_repo_value

    def sandbox_volume_repo(self) -> _FakeRepo:
        return self.sandbox_volume_repo_value

    def thread_launch_pref_repo(self) -> _FakeRepo:
        return self.thread_launch_pref_repo_value

    def recipe_repo(self) -> _FakeRepo:
        return self.recipe_repo_value

    def chat_repo(self) -> _FakeRepo:
        return self.chat_repo_value

    def invite_code_repo(self) -> _FakeRepo:
        return self.invite_code_repo_value

    def user_settings_repo(self) -> _FakeRepo:
        return self.user_settings_repo_value

    def agent_config_repo(self) -> _FakeRepo:
        return self.agent_config_repo_value

    def contact_repo(self) -> _FakeRepo:
        return self.contact_repo_value

    def panel_task_repo(self) -> _FakeRepo:
        return self.panel_task_repo_value

    def cron_job_repo(self) -> _FakeRepo:
        return _FakeRepo()

    def tool_task_repo(self) -> _FakeRepo:
        return _FakeRepo()

    def agent_registry_repo(self) -> _FakeRepo:
        return _FakeRepo()

    def sync_file_repo(self) -> _FakeRepo:
        return _FakeRepo()

    def resource_snapshot_repo(self) -> _FakeRepo:
        return _FakeRepo()


class _FakeMessagingService:
    def __init__(self, **_: object) -> None:
        self.delivery_fn = None

    def set_delivery_fn(self, delivery_fn: object) -> None:
        self.delivery_fn = delivery_fn


class _FakeCronService:
    def __init__(self, **_: object) -> None:
        return None

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


async def _noop_async(*_: object, **__: object) -> None:
    return None


def _fake_repo_factory(*_args: object, **_kwargs: object) -> _FakeRepo:
    return _FakeRepo()


def _install_lifespan_noop_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lifespan_module, "_require_web_runtime_contract", lambda: None)
    monkeypatch.setattr(lifespan_module, "_validate_web_checkpointer_contract", _noop_async)
    monkeypatch.setattr(lifespan_module, "idle_reaper_loop", _noop_async)
    monkeypatch.setattr(lifespan_module, "monitor_resource_overview_refresh_loop", _noop_async)

    monkeypatch.setattr(
        "backend.web.core.supabase_factory.create_supabase_client",
        lambda: _FakeSupabaseClient(),
    )
    monkeypatch.setattr(
        "backend.web.core.supabase_factory.create_public_supabase_client",
        lambda: _FakeSupabaseClient(),
    )
    monkeypatch.setattr(
        "backend.web.core.supabase_factory.create_supabase_auth_client",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        "backend.web.core.supabase_factory.create_messaging_supabase_client",
        lambda: _FakeSupabaseClient(),
    )

    monkeypatch.setattr("storage.providers.supabase.SupabaseUserRepo", _fake_repo_factory)
    monkeypatch.setattr("storage.providers.supabase.SupabaseThreadRepo", _fake_repo_factory)
    monkeypatch.setattr("storage.providers.supabase.SupabaseThreadLaunchPrefRepo", _fake_repo_factory)
    monkeypatch.setattr("storage.providers.supabase.SupabaseRecipeRepo", _fake_repo_factory)
    monkeypatch.setattr("storage.providers.supabase.SupabaseChatRepo", _fake_repo_factory)
    monkeypatch.setattr("storage.providers.supabase.SupabaseInviteCodeRepo", _fake_repo_factory)
    monkeypatch.setattr("storage.providers.supabase.SupabaseUserSettingsRepo", _fake_repo_factory)
    monkeypatch.setattr("storage.providers.supabase.SupabaseContactRepo", _fake_repo_factory)
    monkeypatch.setattr(
        "storage.providers.supabase.agent_config_repo.SupabaseAgentConfigRepo",
        _fake_repo_factory,
    )

    monkeypatch.setattr("backend.web.services.auth_service.AuthService", lambda **_kwargs: object())
    monkeypatch.setattr("backend.web.services.chat_events.ChatEventBus", lambda: object())
    monkeypatch.setattr(
        "backend.web.services.typing_tracker.TypingTracker",
        lambda *_args, **_kwargs: object(),
    )

    monkeypatch.setattr(
        "storage.providers.supabase.messaging_repo.SupabaseChatMemberRepo",
        _fake_repo_factory,
    )
    monkeypatch.setattr(
        "storage.providers.supabase.messaging_repo.SupabaseMessagesRepo",
        _fake_repo_factory,
    )
    monkeypatch.setattr(
        "storage.providers.supabase.messaging_repo.SupabaseMessageReadRepo",
        _fake_repo_factory,
    )
    monkeypatch.setattr(
        "storage.providers.supabase.messaging_repo.SupabaseRelationshipRepo",
        _fake_repo_factory,
    )
    monkeypatch.setattr(
        "messaging.relationships.service.RelationshipService",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        "messaging.delivery.resolver.HireVisitDeliveryResolver",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        "messaging.service.MessagingService",
        lambda **_kwargs: _FakeMessagingService(**_kwargs),
    )
    monkeypatch.setattr(
        "core.agents.communication.delivery.make_chat_delivery_fn",
        lambda _app: object(),
    )

    monkeypatch.setattr("backend.web.services.display_builder.DisplayBuilder", lambda: object())
    monkeypatch.setattr("backend.web.services.cron_service.CronService", _FakeCronService)
    monkeypatch.setattr(
        "core.tools.lsp.service.lsp_pool",
        SimpleNamespace(close_all=_noop_async),
    )


def test_storage_container_exposes_bypass_repo_builders() -> None:
    container = StorageContainer(supabase_client=_FakeSupabaseClient())

    assert callable(container.user_repo)
    assert not hasattr(container, "member_repo")
    assert callable(container.panel_task_repo)
    assert callable(container.cron_job_repo)
    assert callable(container.agent_registry_repo)
    assert callable(container.tool_task_repo)
    assert callable(container.sync_file_repo)
    assert callable(container.resource_snapshot_repo)


def test_storage_container_panel_task_repo_uses_public_client(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakePanelTaskRepo:
        def __init__(self, client: object) -> None:
            captured["client"] = client

    monkeypatch.setattr("storage.providers.supabase.panel_task_repo.SupabasePanelTaskRepo", _FakePanelTaskRepo)

    runtime_client = object()
    public_client = object()
    container = StorageContainer(supabase_client=runtime_client, public_supabase_client=public_client)

    container.panel_task_repo()

    assert captured["client"] is public_client


def test_storage_container_sync_file_repo_uses_public_client(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakeSyncFileRepo:
        def __init__(self, client: object) -> None:
            captured["client"] = client

    monkeypatch.setattr("storage.providers.supabase.sync_file_repo.SupabaseSyncFileRepo", _FakeSyncFileRepo)

    runtime_client = object()
    public_client = object()
    container = StorageContainer(supabase_client=runtime_client, public_supabase_client=public_client)

    container.sync_file_repo()

    assert captured["client"] is public_client


def test_storage_container_user_settings_repo_uses_public_client(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakeUserSettingsRepo:
        def __init__(self, client: object) -> None:
            captured["client"] = client

    monkeypatch.setattr("storage.providers.supabase.user_settings_repo.SupabaseUserSettingsRepo", _FakeUserSettingsRepo)

    runtime_client = object()
    public_client = object()
    container = StorageContainer(supabase_client=runtime_client, public_supabase_client=public_client)

    container.user_settings_repo()

    assert captured["client"] is public_client


def test_make_sandbox_monitor_repo_uses_web_supabase_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakeMonitorRepo:
        def __init__(self, client: object) -> None:
            captured["client"] = client

        def close(self) -> None:
            return None

    fake_client = _FakeSupabaseClient()
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr(
        "backend.web.core.supabase_factory.create_supabase_client",
        lambda: fake_client,
    )
    monkeypatch.setattr(
        "storage.providers.supabase.sandbox_monitor_repo.SupabaseSandboxMonitorRepo",
        _FakeMonitorRepo,
    )

    from backend.web.core import storage_factory

    supabase_cache_clear = getattr(storage_factory._supabase_client, "cache_clear", None)
    if callable(supabase_cache_clear):
        supabase_cache_clear()
    cache_clear = getattr(storage_factory.make_sandbox_monitor_repo, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()

    repo = storage_factory.make_sandbox_monitor_repo()
    try:
        assert isinstance(repo, _FakeMonitorRepo)
        assert captured["client"] is fake_client
    finally:
        repo.close()


def test_make_panel_task_repo_uses_public_supabase_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakePanelTaskRepo:
        def __init__(self, client: object) -> None:
            captured["client"] = client

        def close(self) -> None:
            return None

    fake_client = _FakeSupabaseClient()
    monkeypatch.setattr(
        "backend.web.core.supabase_factory.create_public_supabase_client",
        lambda: fake_client,
    )
    monkeypatch.setattr(
        "storage.providers.supabase.panel_task_repo.SupabasePanelTaskRepo",
        _FakePanelTaskRepo,
    )

    from backend.web.core import storage_factory

    cache_clear = getattr(storage_factory.make_panel_task_repo, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()

    repo = storage_factory.make_panel_task_repo()
    try:
        assert isinstance(repo, _FakePanelTaskRepo)
        assert captured["client"] is fake_client
    finally:
        repo.close()


@pytest.mark.asyncio
async def test_lifespan_wires_user_and_thread_repos_from_storage_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = _FakeContainer()
    app = FastAPI()
    _install_lifespan_noop_dependencies(monkeypatch)
    monkeypatch.setattr("storage.container.StorageContainer", lambda **_: container)

    async with lifespan_module.lifespan(app):
        assert app.state.user_repo is container.user_repo_value
        assert app.state.thread_repo is container.thread_repo_value
        assert app.state.lease_repo is container.lease_repo_value
        assert app.state.terminal_repo is container.terminal_repo_value
        assert app.state.chat_session_repo is container.chat_session_repo_value
        assert app.state.sandbox_volume_repo is container.sandbox_volume_repo_value
        assert app.state.panel_task_repo is container.panel_task_repo_value
        assert not hasattr(app.state, "member_repo")


def test_runtime_services_default_to_storage_runtime_container(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    class _FakeRuntimeContainer:
        def __init__(self) -> None:
            self.tool_task_repo_value = object()
            self.agent_registry_repo_value = object()
            self.sync_file_repo_value = object()

        def tool_task_repo(self) -> object:
            return self.tool_task_repo_value

        def agent_registry_repo(self) -> object:
            return self.agent_registry_repo_value

        def sync_file_repo(self) -> object:
            return self.sync_file_repo_value

    container = _FakeRuntimeContainer()

    monkeypatch.setattr("storage.runtime.build_storage_container", lambda **_kwargs: container)

    task_service = TaskService(registry=ToolRegistry(), db_path=tmp_path / "test.db")
    agent_registry = AgentRegistry()
    sync_state = SyncState()

    assert task_service._repo is container.tool_task_repo_value
    assert agent_registry._repo is container.agent_registry_repo_value
    assert sync_state._repo is container.sync_file_repo_value


def test_resource_snapshot_helpers_default_to_storage_runtime_container(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResourceSnapshotRepo:
        def __init__(self) -> None:
            self.upserts: list[dict[str, object]] = []
            self.snapshots = {"lease-1": {"lease_id": "lease-1", "cpu_used": 1.0}}

        def close(self) -> None:
            return None

        def upsert_lease_resource_snapshot(self, **kwargs: object) -> None:
            self.upserts.append(kwargs)

        def list_snapshots_by_lease_ids(self, lease_ids: list[str]) -> dict[str, dict[str, object]]:
            return {lease_id: self.snapshots[lease_id] for lease_id in lease_ids if lease_id in self.snapshots}

    class _FakeRuntimeContainer:
        def __init__(self) -> None:
            self.resource_snapshot_repo_value = _FakeResourceSnapshotRepo()

        def resource_snapshot_repo(self) -> _FakeResourceSnapshotRepo:
            return self.resource_snapshot_repo_value

    container = _FakeRuntimeContainer()

    monkeypatch.setattr(
        "backend.web.core.storage_factory.list_resource_snapshots",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected web storage factory resource list")),
    )
    monkeypatch.setattr("storage.runtime.build_storage_container", lambda **_kwargs: container)

    resource_snapshot_module.upsert_lease_resource_snapshot(
        lease_id="lease-1",
        provider_name="daytona",
        observed_state="running",
        probe_mode="runtime",
    )
    snapshots = resource_snapshot_module.list_snapshots_by_lease_ids(["lease-1"])

    assert container.resource_snapshot_repo_value.upserts == [
        {
            "lease_id": "lease-1",
            "provider_name": "daytona",
            "observed_state": "running",
            "probe_mode": "runtime",
        }
    ]
    assert snapshots == {"lease-1": {"lease_id": "lease-1", "cpu_used": 1.0}}


def test_build_resource_snapshot_repo_defaults_to_web_supabase_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}

    class _FakeRuntimeContainer:
        def resource_snapshot_repo(self) -> object:
            return object()

    def _fake_build_storage_container(**kwargs: object) -> _FakeRuntimeContainer:
        recorded.update(kwargs)
        return _FakeRuntimeContainer()

    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)
    monkeypatch.setattr("storage.runtime.build_storage_container", _fake_build_storage_container)

    storage_runtime.build_resource_snapshot_repo()

    assert recorded["supabase_client_factory"] == "backend.web.core.supabase_factory:create_supabase_client"


def test_build_sync_file_repo_defaults_to_public_supabase_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}

    class _FakeRuntimeContainer:
        def sync_file_repo(self) -> object:
            return object()

    def _fake_build_storage_container(**kwargs: object) -> _FakeRuntimeContainer:
        recorded.update(kwargs)
        return _FakeRuntimeContainer()

    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)
    monkeypatch.setattr("storage.runtime.build_storage_container", _fake_build_storage_container)

    storage_runtime.build_sync_file_repo()

    assert recorded["public_supabase_client_factory"] == "backend.web.core.supabase_factory:create_public_supabase_client"
