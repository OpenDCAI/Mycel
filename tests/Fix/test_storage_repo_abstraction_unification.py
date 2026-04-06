from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from backend.web.core import lifespan as lifespan_module
from storage.container import StorageContainer


class _FakeSupabaseClient:
    pass


class _FakeRepo:
    def close(self) -> None:
        return None


class _FakeContainer:
    def __init__(self) -> None:
        self.member_repo_value = _FakeRepo()
        self.thread_repo_value = _FakeRepo()
        self.thread_launch_pref_repo_value = _FakeRepo()
        self.recipe_repo_value = _FakeRepo()
        self.chat_repo_value = _FakeRepo()
        self.invite_code_repo_value = _FakeRepo()
        self.user_settings_repo_value = _FakeRepo()
        self.agent_config_repo_value = _FakeRepo()
        self.contact_repo_value = _FakeRepo()

    def member_repo(self) -> _FakeRepo:
        return self.member_repo_value

    def thread_repo(self) -> _FakeRepo:
        return self.thread_repo_value

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


class _FakeMessagingService:
    def __init__(self, **_: object) -> None:
        self.delivery_fn = None

    def set_delivery_fn(self, delivery_fn: object) -> None:
        self.delivery_fn = delivery_fn


class _FakeCronService:
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
        "backend.web.core.supabase_factory.create_supabase_auth_client",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        "backend.web.core.supabase_factory.create_messaging_supabase_client",
        lambda: _FakeSupabaseClient(),
    )

    monkeypatch.setattr("storage.providers.supabase.SupabaseMemberRepo", _fake_repo_factory)
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

    assert callable(container.panel_task_repo)
    assert callable(container.cron_job_repo)
    assert callable(container.agent_registry_repo)
    assert callable(container.tool_task_repo)
    assert callable(container.sync_file_repo)


@pytest.mark.asyncio
async def test_lifespan_wires_member_and_thread_repos_from_storage_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = _FakeContainer()
    app = FastAPI()
    _install_lifespan_noop_dependencies(monkeypatch)
    monkeypatch.setattr("storage.container.StorageContainer", lambda **_: container)

    async with lifespan_module.lifespan(app):
        assert app.state.member_repo is container.member_repo_value
        assert app.state.thread_repo is container.thread_repo_value
