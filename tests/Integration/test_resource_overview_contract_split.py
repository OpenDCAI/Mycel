from __future__ import annotations

import asyncio
import inspect

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.web.core.dependencies import get_current_user_id
from backend.web.main import app
from backend.web.routers import monitor as monitor_router
from backend.web.routers import resources as resources_router
from backend.web.services import resource_projection_service, resource_service


def test_resource_services_no_longer_import_storage_factory() -> None:
    resource_service_source = inspect.getsource(resource_service)
    projection_service_source = inspect.getsource(resource_projection_service)

    assert "backend.web.core.storage_factory" not in resource_service_source
    assert "backend.web.core.storage_factory" not in projection_service_source
    assert "storage.runtime" in resource_service_source
    assert "storage.runtime" in projection_service_source


def test_resources_overview_route_exists() -> None:
    assert any(getattr(route, "path", None) == "/api/resources/overview" for route in app.routes)


def test_resources_overview_maps_runtime_error_to_500(monkeypatch) -> None:
    monkeypatch.setattr(
        resource_projection_service,
        "list_user_resource_providers",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )

    request = type("_Request", (), {"app": object()})()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            resources_router.resources_overview(
                user_id="user-1",
                request=request,
            )
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "provider unavailable"


def test_monitor_resources_route_stays_global(monkeypatch) -> None:
    monkeypatch.setattr(
        monitor_router,
        "get_monitor_resource_overview_snapshot",
        lambda: {"summary": {"snapshot_at": "now"}, "providers": [{"id": "global-daytona"}]},
    )

    test_app = FastAPI()
    test_app.include_router(monitor_router.router)
    test_app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    try:
        with TestClient(test_app) as client:
            response = client.get("/api/monitor/resources")
    finally:
        test_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["providers"][0]["id"] == "global-daytona"


def test_user_resource_projection_groups_visible_leases_into_provider_cards(monkeypatch) -> None:
    class _State:
        thread_repo = object()
        user_repo = object()

    class _App:
        state = _State()

    monkeypatch.setattr(
        resource_projection_service.sandbox_service,
        "list_user_leases",
        lambda owner_user_id, **_kwargs: [
            {
                "lease_id": "lease-1",
                "provider_name": "daytona_selfhost",
                "recipe": {"id": "daytona:default", "provider_type": "daytona", "name": "Daytona Default"},
                "cwd": "/home/daytona/app",
                "thread_ids": ["thread-1"],
                "agents": [
                    {
                        "agent_user_id": "agent-1",
                        "agent_name": "Morel",
                        "avatar_url": "/api/users/agent-1/avatar",
                    }
                ],
                "observed_state": "running",
                "desired_state": "running",
                "created_at": "2026-04-07T10:00:00Z",
                "runtime_session_id": "provider-session-1",
            }
        ],
    )
    monkeypatch.setattr(
        resource_projection_service.resource_service,
        "get_provider_display_contract",
        lambda *_args, **_kwargs: {
            "provider_name": "daytona",
            "description": "Daytona",
            "vendor": "Daytona",
            "type": "cloud",
            "console_url": "https://example.com/daytona",
        },
        raising=False,
    )
    monkeypatch.setattr(
        resource_projection_service.resource_service,
        "get_provider_capability_contract",
        lambda *_args, **_kwargs: (resource_projection_service._empty_capabilities(), None),
        raising=False,
    )

    payload = resource_projection_service.list_user_resource_providers(_App(), "owner-1")

    assert payload["summary"]["total_providers"] == 1
    assert payload["summary"]["running_sessions"] == 1
    assert payload["providers"][0]["id"] == "daytona_selfhost"
    assert payload["providers"][0]["description"] == "Daytona"
    assert payload["providers"][0]["vendor"] == "Daytona"
    assert payload["providers"][0]["type"] == "cloud"
    assert payload["providers"][0]["consoleUrl"] == "https://example.com/daytona"
    assert payload["providers"][0]["sessions"][0]["leaseId"] == "lease-1"
    assert payload["providers"][0]["sessions"][0]["threadId"] == "thread-1"
    assert payload["providers"][0]["sessions"][0]["agentUserId"] == "agent-1"
    assert payload["providers"][0]["sessions"][0]["agentName"] == "Morel"
    assert payload["providers"][0]["sessions"][0]["avatarUrl"] == "/api/users/agent-1/avatar"
    assert payload["providers"][0]["sessions"][0]["runtimeSessionId"] == "provider-session-1"
    assert payload["providers"][0]["sessions"][0]["startedAt"] == "2026-04-07T10:00:00Z"
    assert "memberId" not in payload["providers"][0]["sessions"][0]
    assert "memberName" not in payload["providers"][0]["sessions"][0]


def test_user_resource_projection_marks_provider_unavailable_when_capability_probe_fails(monkeypatch) -> None:
    class _State:
        thread_repo = object()
        user_repo = object()

    class _App:
        state = _State()

    monkeypatch.setattr(
        resource_projection_service.sandbox_service,
        "list_user_leases",
        lambda owner_user_id, **_kwargs: [
            {
                "lease_id": "lease-1",
                "provider_name": "daytona_selfhost",
                "thread_ids": ["thread-1"],
                "agents": [{"agent_user_id": "agent-1", "agent_name": "Morel", "avatar_url": "/api/users/agent-1/avatar"}],
                "observed_state": "paused",
                "desired_state": "paused",
                "created_at": "2026-04-07T10:00:00Z",
                "runtime_session_id": "provider-session-1",
            }
        ],
    )
    monkeypatch.setattr(
        resource_projection_service.resource_service,
        "get_provider_display_contract",
        lambda *_args, **_kwargs: {
            "provider_name": "daytona",
            "description": "Daytona",
            "vendor": "Daytona",
            "type": "cloud",
            "console_url": "https://example.com/daytona",
        },
        raising=False,
    )
    monkeypatch.setattr(
        resource_projection_service.resource_service,
        "get_provider_capability_contract",
        lambda *_args, **_kwargs: (resource_projection_service._empty_capabilities(), "provider unavailable"),
        raising=False,
    )

    payload = resource_projection_service.list_user_resource_providers(_App(), "owner-1")

    assert payload["providers"][0]["status"] == "unavailable"
    assert payload["providers"][0]["unavailableReason"] == "provider unavailable"
    assert payload["providers"][0]["error"] == {
        "code": "PROVIDER_UNAVAILABLE",
        "message": "provider unavailable",
    }
    assert payload["providers"][0]["sessions"][0]["runtimeSessionId"] == "provider-session-1"
    assert payload["providers"][0]["sessions"][0]["agentUserId"] == "agent-1"
    assert payload["providers"][0]["sessions"][0]["agentName"] == "Morel"
    assert payload["providers"][0]["sessions"][0]["avatarUrl"] == "/api/users/agent-1/avatar"
    assert "memberId" not in payload["providers"][0]["sessions"][0]
    assert "memberName" not in payload["providers"][0]["sessions"][0]


def test_user_resource_projection_only_backfills_remote_runtime_ids(monkeypatch) -> None:
    class _State:
        thread_repo = object()
        user_repo = object()

    class _App:
        state = _State()

    class _FakeMonitorRepo:
        def __init__(self) -> None:
            self.batch_calls: list[list[str]] = []

        def query_lease_instance_id(self, lease_id: str) -> str | None:
            raise AssertionError(f"unexpected per-lease runtime-session probe: {lease_id}")

        def query_lease_instance_ids(self, lease_ids: list[str]) -> dict[str, str | None]:
            self.batch_calls.append(list(lease_ids))
            return {
                "lease-local": None,
                "lease-remote": "provider-session-remote",
            }

        def close(self) -> None:
            return None

    monitor_repo = _FakeMonitorRepo()

    def _fake_list_user_leases(owner_user_id: str, **kwargs):
        assert kwargs.get("include_runtime_session_id") in {None, False}
        return [
            {
                "lease_id": "lease-local",
                "provider_name": "local",
                "thread_ids": ["thread-local"],
                "agents": [{"agent_user_id": "agent-local", "agent_name": "Local", "avatar_url": None}],
                "observed_state": "detached",
                "desired_state": "running",
                "created_at": "2026-04-07T10:00:00Z",
            },
            {
                "lease_id": "lease-remote",
                "provider_name": "daytona_selfhost",
                "thread_ids": ["thread-remote"],
                "agents": [{"agent_user_id": "agent-remote", "agent_name": "Remote", "avatar_url": None}],
                "observed_state": "detached",
                "desired_state": "running",
                "created_at": "2026-04-07T10:00:01Z",
            },
        ]

    monkeypatch.setattr(resource_projection_service.sandbox_service, "list_user_leases", _fake_list_user_leases)
    monkeypatch.setattr(resource_projection_service, "make_sandbox_monitor_repo", lambda: monitor_repo)
    monkeypatch.setattr(
        resource_projection_service.resource_service,
        "get_provider_display_contract",
        lambda config_name, *_args, **_kwargs: {
            "provider_name": "local" if config_name == "local" else "daytona",
            "description": config_name,
            "vendor": config_name,
            "type": "local" if config_name == "local" else "cloud",
            "console_url": None,
        },
        raising=False,
    )
    monkeypatch.setattr(
        resource_projection_service.resource_service,
        "get_provider_capability_contract",
        lambda *_args, **_kwargs: (resource_projection_service._empty_capabilities(), None),
        raising=False,
    )

    payload = resource_projection_service.list_user_resource_providers(_App(), "owner-1")

    providers = {item["id"]: item for item in payload["providers"]}
    assert "runtimeSessionId" not in providers["local"]["sessions"][0]
    assert providers["daytona_selfhost"]["sessions"][0]["runtimeSessionId"] == "provider-session-remote"
    assert monitor_repo.batch_calls == [["lease-local", "lease-remote"]]


def test_user_resource_projection_uses_batch_runtime_backfill_for_remote_leases(monkeypatch) -> None:
    class _State:
        thread_repo = object()
        user_repo = object()

    class _App:
        state = _State()

    class _FakeMonitorRepo:
        def __init__(self) -> None:
            self.batch_calls: list[list[str]] = []

        def query_lease_instance_id(self, lease_id: str) -> str | None:
            raise AssertionError(f"unexpected per-lease runtime-session probe: {lease_id}")

        def query_lease_instance_ids(self, lease_ids: list[str]) -> dict[str, str | None]:
            self.batch_calls.append(list(lease_ids))
            return {
                "lease-remote-a": "provider-session-a",
                "lease-remote-b": "provider-session-b",
            }

        def close(self) -> None:
            return None

    monitor_repo = _FakeMonitorRepo()

    monkeypatch.setattr(
        resource_projection_service.sandbox_service,
        "list_user_leases",
        lambda owner_user_id, **kwargs: [
            {
                "lease_id": "lease-remote-a",
                "provider_name": "daytona_selfhost",
                "thread_ids": ["thread-a"],
                "agents": [{"agent_user_id": "agent-a", "agent_name": "A", "avatar_url": None}],
                "observed_state": "detached",
                "desired_state": "running",
                "created_at": "2026-04-07T10:00:00Z",
            },
            {
                "lease_id": "lease-remote-b",
                "provider_name": "daytona_selfhost",
                "thread_ids": ["thread-b"],
                "agents": [{"agent_user_id": "agent-b", "agent_name": "B", "avatar_url": None}],
                "observed_state": "detached",
                "desired_state": "running",
                "created_at": "2026-04-07T10:00:01Z",
            },
        ],
    )
    monkeypatch.setattr(resource_projection_service, "make_sandbox_monitor_repo", lambda: monitor_repo)
    monkeypatch.setattr(
        resource_projection_service.resource_service,
        "get_provider_display_contract",
        lambda *_args, **_kwargs: {
            "provider_name": "daytona",
            "description": "daytona",
            "vendor": "daytona",
            "type": "cloud",
            "console_url": None,
        },
        raising=False,
    )
    monkeypatch.setattr(
        resource_projection_service.resource_service,
        "get_provider_capability_contract",
        lambda *_args, **_kwargs: (resource_projection_service._empty_capabilities(), None),
        raising=False,
    )

    payload = resource_projection_service.list_user_resource_providers(_App(), "owner-1")

    sessions = payload["providers"][0]["sessions"]
    assert [session["runtimeSessionId"] for session in sessions] == ["provider-session-a", "provider-session-b"]
    assert monitor_repo.batch_calls == [["lease-remote-a", "lease-remote-b"]]


def test_resources_overview_route_surfaces_actor_first_user_payload(monkeypatch) -> None:
    class _State:
        thread_repo = object()
        user_repo = object()

    test_app = FastAPI()
    test_app.state = _State()
    test_app.include_router(resources_router.router)
    test_app.dependency_overrides[get_current_user_id] = lambda: "owner-1"

    monkeypatch.setattr(
        resource_projection_service.sandbox_service,
        "list_user_leases",
        lambda owner_user_id, **_kwargs: [
            {
                "lease_id": "lease-1",
                "provider_name": "daytona_selfhost",
                "thread_ids": ["thread-1"],
                "agents": [
                    {
                        "agent_user_id": "agent-1",
                        "agent_name": "Morel",
                        "avatar_url": "/api/users/agent-1/avatar",
                    }
                ],
                "observed_state": "running",
                "desired_state": "running",
                "created_at": "2026-04-07T10:00:00Z",
                "runtime_session_id": "provider-session-1",
            }
        ],
    )
    monkeypatch.setattr(
        resource_projection_service.resource_service,
        "get_provider_display_contract",
        lambda *_args, **_kwargs: {
            "provider_name": "daytona",
            "description": "Daytona",
            "vendor": "Daytona",
            "type": "cloud",
            "console_url": "https://example.com/daytona",
        },
        raising=False,
    )
    monkeypatch.setattr(
        resource_projection_service.resource_service,
        "get_provider_capability_contract",
        lambda *_args, **_kwargs: (resource_projection_service._empty_capabilities(), None),
        raising=False,
    )

    try:
        with TestClient(test_app) as client:
            response = client.get("/api/resources/overview")
    finally:
        test_app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    session = payload["providers"][0]["sessions"][0]
    assert payload["summary"]["scope"] == "user"
    assert payload["providers"][0]["id"] == "daytona_selfhost"
    assert session["runtimeSessionId"] == "provider-session-1"
    assert session["agentUserId"] == "agent-1"
    assert session["agentName"] == "Morel"
    assert session["avatarUrl"] == "/api/users/agent-1/avatar"
    assert "memberId" not in session
    assert "memberName" not in session


def test_provider_display_contract_exposes_public_metadata(monkeypatch) -> None:
    monkeypatch.setattr(resource_service, "resolve_provider_name", lambda *_args, **_kwargs: "daytona")
    monkeypatch.setattr(
        resource_service,
        "_resolve_provider_type",
        lambda *_args, **_kwargs: "cloud",
    )
    monkeypatch.setattr(
        resource_service,
        "_resolve_console_url",
        lambda *_args, **_kwargs: "https://example.com/daytona",
    )
    monkeypatch.setattr(
        resource_service,
        "_CATALOG",
        {"daytona": type("_Catalog", (), {"description": "Daytona", "vendor": "Daytona"})()},
    )

    payload = resource_service.get_provider_display_contract("daytona_selfhost")

    assert payload == {
        "provider_name": "daytona",
        "description": "Daytona",
        "vendor": "Daytona",
        "type": "cloud",
        "console_url": "https://example.com/daytona",
    }
