from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.web.core.dependencies import get_current_user_id
from backend.web.main import app
from backend.web.routers import monitor as monitor_router
from backend.web.services import resource_projection_service, resource_service


def test_resources_overview_route_exists() -> None:
    assert any(getattr(route, "path", None) == "/api/resources/overview" for route in app.routes)


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
        member_repo = object()

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
                        "member_id": "member-1",
                        "member_name": "Morel",
                        "avatar_url": "/api/members/member-1/avatar",
                    }
                ],
                "observed_state": "running",
                "desired_state": "running",
                "created_at": "2026-04-07T10:00:00Z",
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
    assert payload["providers"][0]["sessions"][0]["memberName"] == "Morel"
    assert payload["providers"][0]["sessions"][0]["startedAt"] == "2026-04-07T10:00:00Z"


def test_user_resource_projection_marks_provider_unavailable_when_capability_probe_fails(monkeypatch) -> None:
    class _State:
        thread_repo = object()
        member_repo = object()

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
                "agents": [{"member_id": "member-1", "member_name": "Morel", "avatar_url": None}],
                "observed_state": "paused",
                "desired_state": "paused",
                "created_at": "2026-04-07T10:00:00Z",
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
