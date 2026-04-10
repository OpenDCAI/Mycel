from __future__ import annotations

from types import SimpleNamespace

from backend.web.services import resource_projection_service, resource_service, sandbox_service
from backend.web.utils.serializers import avatar_url


def test_list_user_leases_exposes_thread_identity_not_member_id(monkeypatch) -> None:
    class _FakeMonitorRepo:
        def list_leases_with_threads(self) -> list[dict[str, object]]:
            return [
                {
                    "lease_id": "lease-1",
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

    result = sandbox_service.list_user_leases("owner-1", thread_repo=thread_repo, user_repo=user_repo)

    assert len(result) == 1
    lease = result[0]
    assert lease["lease_id"] == "lease-1"
    assert lease["provider_name"] == "daytona_selfhost"
    assert lease["thread_ids"] == ["thread-1"]
    assert lease["recipe_id"] == "daytona:default"
    assert lease["recipe_name"] == "Daytona Default"
    assert lease["recipe"]["id"] == "daytona:default"
    assert lease["recipe"]["provider_type"] == "daytona"
    assert lease["agents"] == [
        {
            "thread_id": "thread-1",
            "agent_user_id": "agent-1",
            "agent_name": "Morel",
            "avatar_url": avatar_url("agent-1", True),
        }
    ]
    assert "member_id" not in lease["agents"][0]


def test_resource_projection_sessions_do_not_leak_member_ids(monkeypatch) -> None:
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
                "cwd": "/workspace",
                "thread_ids": ["thread-1"],
                "agents": [
                    {
                        "thread_id": "thread-1",
                        "agent_name": "Morel",
                        "avatar_url": avatar_url("member-1", True),
                    }
                ],
                "observed_state": "running",
                "desired_state": "running",
                "created_at": "2026-04-08T10:00:00Z",
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
    monkeypatch.setattr(
        resource_projection_service,
        "make_sandbox_monitor_repo",
        lambda: SimpleNamespace(query_lease_instance_ids=lambda _lease_ids: {}, close=lambda: None),
    )

    payload = resource_projection_service.list_user_resource_providers(_App(), "owner-1")

    session = payload["providers"][0]["sessions"][0]
    assert session["threadId"] == "thread-1"
    assert session["agentName"] == "Morel"
    assert session["avatarUrl"] == avatar_url("member-1", True)
    assert "memberId" not in session


def test_build_resource_session_payload_has_no_member_id_field() -> None:
    payload = resource_service.build_resource_session_payload(
        session_identity="lease-1:thread-1",
        lease_id="lease-1",
        thread_id="thread-1",
        runtime_session_id="provider-session-1",
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
        "id": "lease-1:thread-1",
        "leaseId": "lease-1",
        "threadId": "thread-1",
        "runtimeSessionId": "provider-session-1",
        "agentUserId": "agent-1",
        "agentName": "Toad",
        "avatarUrl": "/api/users/agent-1/avatar",
        "status": "running",
        "startedAt": "2026-04-08T10:00:00Z",
        "metrics": None,
    }
    assert "memberId" not in payload
