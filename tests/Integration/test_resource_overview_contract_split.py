from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.web.core.dependencies import get_current_user_id
from backend.web.routers import monitor as monitor_router
from backend.web.routers import resources as resources_router
from backend.web.services import resource_projection_service


class _State:
    thread_repo = object()
    user_repo = object()


class _App:
    state = _State()


class _FakeMonitorRepo:
    def __init__(self, runtime_session_ids: dict[str, str | None]) -> None:
        self._runtime_session_ids = runtime_session_ids
        self.batch_calls: list[list[str]] = []

    def query_lease_instance_id(self, lease_id: str) -> str | None:
        raise AssertionError(f"unexpected per-lease runtime-session probe: {lease_id}")

    def query_lease_instance_ids(self, lease_ids: list[str]) -> dict[str, str | None]:
        self.batch_calls.append(list(lease_ids))
        return {
            lease_id: self._runtime_session_ids.get(lease_id)
            for lease_id in lease_ids
        }

    def close(self) -> None:
        return None


def _patch_provider_contracts(monkeypatch, *, description: str, vendor: str, type_: str, console_url: str | None) -> None:
    monkeypatch.setattr(
        resource_projection_service.resource_service,
        "get_provider_display_contract",
        lambda config_name, *_args, **_kwargs: {
            "provider_name": "local" if config_name == "local" else "daytona",
            "description": description if config_name != "local" else "local",
            "vendor": vendor if config_name != "local" else "local",
            "type": type_ if config_name != "local" else "local",
            "console_url": console_url if config_name != "local" else None,
        },
        raising=False,
    )
    monkeypatch.setattr(
        resource_projection_service.resource_service,
        "get_provider_capability_contract",
        lambda *_args, **_kwargs: (resource_projection_service._empty_capabilities(), None),
        raising=False,
    )


def _lease(
    lease_id: str,
    *,
    provider_name: str = "daytona_selfhost",
    thread_id: str,
    agent_user_id: str,
    agent_name: str,
    avatar_url: str | None,
    observed_state: str = "running",
    desired_state: str = "running",
    created_at: str = "2026-04-07T10:00:00Z",
    runtime_session_id: str | None = None,
    cwd: str | None = None,
    recipe: dict | None = None,
) -> dict:
    payload = {
        "lease_id": lease_id,
        "provider_name": provider_name,
        "thread_ids": [thread_id],
        "agents": [{"agent_user_id": agent_user_id, "agent_name": agent_name, "avatar_url": avatar_url}],
        "observed_state": observed_state,
        "desired_state": desired_state,
        "created_at": created_at,
    }
    if runtime_session_id is not None:
        payload["runtime_session_id"] = runtime_session_id
    if cwd is not None:
        payload["cwd"] = cwd
    if recipe is not None:
        payload["recipe"] = recipe
    return payload


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
    monkeypatch.setattr(
        resource_projection_service.sandbox_service,
        "list_user_leases",
        lambda owner_user_id, **_kwargs: [
            _lease(
                "lease-1",
                thread_id="thread-1",
                agent_user_id="agent-1",
                agent_name="Morel",
                avatar_url="/api/users/agent-1/avatar",
                runtime_session_id="provider-session-1",
                cwd="/home/daytona/app",
                recipe={"id": "daytona:default", "provider_type": "daytona", "name": "Daytona Default"},
            )
        ],
    )
    _patch_provider_contracts(
        monkeypatch,
        description="Daytona",
        vendor="Daytona",
        type_="cloud",
        console_url="https://example.com/daytona",
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
    monkeypatch.setattr(
        resource_projection_service.sandbox_service,
        "list_user_leases",
        lambda owner_user_id, **_kwargs: [
            _lease(
                "lease-1",
                thread_id="thread-1",
                agent_user_id="agent-1",
                agent_name="Morel",
                avatar_url="/api/users/agent-1/avatar",
                observed_state="paused",
                desired_state="paused",
                runtime_session_id="provider-session-1",
            )
        ],
    )
    _patch_provider_contracts(
        monkeypatch,
        description="Daytona",
        vendor="Daytona",
        type_="cloud",
        console_url="https://example.com/daytona",
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


@pytest.mark.parametrize(
    ("leases", "runtime_session_ids", "assertions"),
    [
        (
            [
                _lease(
                    "lease-local",
                    provider_name="local",
                    thread_id="thread-local",
                    agent_user_id="agent-local",
                    agent_name="Local",
                    avatar_url=None,
                    observed_state="detached",
                    desired_state="running",
                ),
                _lease(
                    "lease-remote",
                    thread_id="thread-remote",
                    agent_user_id="agent-remote",
                    agent_name="Remote",
                    avatar_url=None,
                    observed_state="detached",
                    desired_state="running",
                    created_at="2026-04-07T10:00:01Z",
                ),
            ],
            {"lease-local": None, "lease-remote": "provider-session-remote"},
            lambda payload: (
                "runtimeSessionId" not in {item["id"]: item for item in payload["providers"]}["local"]["sessions"][0],
                {item["id"]: item for item in payload["providers"]}["daytona_selfhost"]["sessions"][0]["runtimeSessionId"]
                == "provider-session-remote",
            ),
        ),
        (
            [
                _lease(
                    "lease-remote-a",
                    thread_id="thread-a",
                    agent_user_id="agent-a",
                    agent_name="A",
                    avatar_url=None,
                    observed_state="detached",
                    desired_state="running",
                ),
                _lease(
                    "lease-remote-b",
                    thread_id="thread-b",
                    agent_user_id="agent-b",
                    agent_name="B",
                    avatar_url=None,
                    observed_state="detached",
                    desired_state="running",
                    created_at="2026-04-07T10:00:01Z",
                ),
            ],
            {"lease-remote-a": "provider-session-a", "lease-remote-b": "provider-session-b"},
            lambda payload: (
                [session["runtimeSessionId"] for session in payload["providers"][0]["sessions"]]
                == ["provider-session-a", "provider-session-b"],
            ),
        ),
    ],
    ids=["skip-local-backfill", "batch-backfill-remote-only"],
)
def test_user_resource_projection_runtime_backfill_contract(monkeypatch, leases, runtime_session_ids, assertions) -> None:
    monitor_repo = _FakeMonitorRepo(runtime_session_ids)

    def _fake_list_user_leases(owner_user_id: str, **kwargs):
        assert kwargs.get("include_runtime_session_id") in {None, False}
        return leases

    monkeypatch.setattr(resource_projection_service.sandbox_service, "list_user_leases", _fake_list_user_leases)
    monkeypatch.setattr(resource_projection_service, "make_sandbox_monitor_repo", lambda: monitor_repo)
    _patch_provider_contracts(
        monkeypatch,
        description="daytona",
        vendor="daytona",
        type_="cloud",
        console_url=None,
    )

    payload = resource_projection_service.list_user_resource_providers(_App(), "owner-1")

    assert all(assertions(payload))
    assert monitor_repo.batch_calls == [[lease["lease_id"] for lease in leases]]


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
            _lease(
                "lease-1",
                thread_id="thread-1",
                agent_user_id="agent-1",
                agent_name="Morel",
                avatar_url="/api/users/agent-1/avatar",
                runtime_session_id="provider-session-1",
            )
        ],
    )
    _patch_provider_contracts(
        monkeypatch,
        description="Daytona",
        vendor="Daytona",
        type_="cloud",
        console_url="https://example.com/daytona",
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
