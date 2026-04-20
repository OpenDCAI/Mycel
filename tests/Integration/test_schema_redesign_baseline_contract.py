from __future__ import annotations

import inspect
from types import SimpleNamespace

import backend.resource_projection as resource_projection_service
import backend.resource_provider_boundary as resource_provider_boundary_service
from backend import resource_common
from backend import resource_provider_contracts as resource_service
from backend.monitor.infrastructure.read_models import resource_read_service as monitor_resource_read_service
from backend.web.services import (
    sandbox_service,
)
from backend.web.utils.serializers import avatar_url


def test_list_user_sandboxes_exposes_thread_identity_not_member_id(monkeypatch) -> None:
    class _FakeMonitorRepo:
        def query_sandboxes(self) -> list[dict[str, object]]:
            return [
                {
                    "lease_" + "id": "lease-1",
                    "sandbox_id": "sandbox-1",
                    "provider_name": "daytona_selfhost",
                    "recipe_id": "daytona:default",
                    "recipe_json": None,
                    "observed_state": "running",
                    "desired_state": "running",
                    "created_at": "2026-04-08T00:00:00Z",
                    "cwd": "/workspace",
                    "thread_id": "thread-1",
                }
            ]

        def close(self) -> None:
            return None

    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda: _FakeMonitorRepo())
    thread_repo = SimpleNamespace(
        list_by_owner_user_id=lambda owner_user_id: (
            [{"id": "thread-1", "agent_user_id": "agent-1", "owner_user_id": owner_user_id}] if owner_user_id == "owner-1" else []
        )
    )
    user_repo = SimpleNamespace(
        list_by_owner_user_id=lambda owner_user_id: (
            [
                SimpleNamespace(
                    id="agent-1",
                    display_name="Morel",
                    avatar="avatars/morel.png",
                    owner_user_id=owner_user_id,
                )
            ]
            if owner_user_id == "owner-1"
            else []
        )
    )

    result = sandbox_service.list_user_sandboxes("owner-1", thread_repo=thread_repo, user_repo=user_repo)

    assert len(result) == 1
    sandbox = result[0]
    assert "lease_" + "id" not in sandbox
    assert sandbox["provider_name"] == "daytona_selfhost"
    assert sandbox["thread_ids"] == ["thread-1"]
    assert sandbox["recipe_id"] == "daytona_selfhost:default"
    assert sandbox["recipe_name"] == "Daytona Selfhost Default"
    assert sandbox["recipe"]["id"] == "daytona_selfhost:default"
    assert sandbox["recipe"]["provider_name"] == "daytona_selfhost"
    assert sandbox["recipe"]["provider_type"] == "daytona"
    assert sandbox["agents"] == [
        {
            "thread_id": "thread-1",
            "agent_user_id": "agent-1",
            "agent_name": "Morel",
            "avatar_url": avatar_url("agent-1", True),
        }
    ]
    assert "member_id" not in sandbox["agents"][0]


def test_resource_projection_rows_do_not_leak_member_ids(monkeypatch) -> None:
    class _State:
        thread_repo = object()
        user_repo = object()

    class _App:
        state = _State()

    monkeypatch.setattr(
        resource_provider_boundary_service,
        "load_user_sandboxes",
        lambda _app, _owner_user_id: [
            {
                "sandbox_id": "sandbox-1",
                "provider_name": "daytona_selfhost",
                "recipe": {"id": "daytona:default", "provider_type": "daytona", "name": "Daytona Default"},
                "cwd": "/workspace",
                "thread_ids": ["thread-1"],
                "agents": [
                    {
                        "thread_id": "thread-1",
                        "agent_name": "Morel",
                        "avatar_url": avatar_url("agent-user-1", True),
                    }
                ],
                "observed_state": "running",
                "desired_state": "running",
                "created_at": "2026-04-08T10:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        resource_provider_boundary_service,
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
        resource_provider_boundary_service,
        "get_provider_capability_contract",
        lambda *_args, **_kwargs: (resource_common.empty_capabilities(), None),
        raising=False,
    )
    monkeypatch.setattr(
        monitor_resource_read_service,
        "make_sandbox_monitor_repo",
        lambda: SimpleNamespace(query_sandbox_instance_ids=lambda _sandbox_ids: {}, close=lambda: None),
    )

    payload = resource_projection_service.list_user_resource_providers(_App(), "owner-1")

    provider = payload["providers"][0]
    assert "sess" + "ions" not in provider
    row = provider["resource_rows"][0]
    assert row["sandboxId"] == "sandbox-1"
    assert row["threadId"] == "thread-1"
    assert row["agentName"] == "Morel"
    assert row["avatarUrl"] == avatar_url("agent-user-1", True)
    assert "lease" + "Id" not in row
    assert "memberId" not in row


def test_build_resource_row_payload_has_no_member_or_lower_runtime_identity_field() -> None:
    signature = inspect.signature(resource_service.build_resource_row_payload)
    assert "lease_" + "id" not in signature.parameters

    payload = resource_service.build_resource_row_payload(
        resource_identity="sandbox-1:thread-1",
        sandbox_id="sandbox-1",
        thread_id="thread-1",
        runtime_id="provider-session-1",
        owner={
            "thread_id": "thread-1",
            "agent_user_id": "agent-1",
            "agent_name": "Toad",
            "avatar_url": "/api/users/agent-1/avatar",
        },
        status="running",
        started_at="2026-04-08T10:00:00Z",
        metrics=None,
    )

    assert payload == {
        "id": "sandbox-1:thread-1",
        "sandboxId": "sandbox-1",
        "threadId": "thread-1",
        "runtimeId": "provider-session-1",
        "agentUserId": "agent-1",
        "agentName": "Toad",
        "avatarUrl": "/api/users/agent-1/avatar",
        "status": "running",
        "startedAt": "2026-04-08T10:00:00Z",
        "metrics": None,
    }
    assert "memberId" not in payload
    assert "lease" + "Id" not in payload
