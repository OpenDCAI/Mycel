from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.web.services import thread_state_service
from backend.web.services.thread_state_service import get_sandbox_info, get_sandbox_status_from_repos


def test_thread_state_service_uses_runtime_row_language_not_lease_read_model() -> None:
    source = thread_state_service.__loader__.get_source(thread_state_service.__name__)

    assert source is not None
    assert "_lease_from_runtime_binding" not in source
    assert "lease_repo.find_by_instance is required for thread sandbox status" not in source
    assert 'label="lease"' not in source


def test_sandbox_info_does_not_expose_terminal_or_session_identity() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(
                get_by_id=lambda thread_id: {
                    "id": thread_id,
                    "owner_user_id": "owner-1",
                    "agent_user_id": "agent-user-1",
                    "current_workspace_id": "workspace-1",
                }
            ),
            workspace_repo=SimpleNamespace(
                get_by_id=lambda workspace_id: {
                    "id": workspace_id,
                    "owner_user_id": "owner-1",
                    "sandbox_id": "sandbox-1",
                    "workspace_path": "/workspace",
                }
            ),
            sandbox_repo=SimpleNamespace(
                get_by_id=lambda sandbox_id: {
                    "id": sandbox_id,
                    "owner_user_id": "owner-1",
                    "provider_name": "daytona",
                    "provider_env_id": "instance-1",
                    "config": {},
                }
            ),
            lease_repo=SimpleNamespace(
                get=lambda _lease_id: (_ for _ in ()).throw(AssertionError("sandbox info should not read legacy lease id")),
                find_by_instance=lambda *, provider_name, instance_id: {
                    "lease_id": "lease-1",
                    "provider_name": provider_name,
                    "current_instance_id": instance_id,
                    "observed_state": "running",
                    "_instance": {"status": "running", "instance_id": instance_id},
                },
            ),
            terminal_repo=SimpleNamespace(
                get_active=lambda _thread_id: (_ for _ in ()).throw(AssertionError("sandbox info should not read terminal rows"))
            ),
        )
    )

    payload = get_sandbox_info(app, "thread-1", "daytona")

    assert payload == {"type": "daytona", "status": "running"}


@pytest.mark.asyncio
async def test_sandbox_status_resolves_lease_from_provider_env_not_legacy_config() -> None:
    thread_repo = SimpleNamespace(
        get_by_id=lambda thread_id: {
            "id": thread_id,
            "owner_user_id": "owner-1",
            "agent_user_id": "agent-user-1",
            "current_workspace_id": "workspace-1",
        }
    )
    workspace_repo = SimpleNamespace(
        get_by_id=lambda workspace_id: {
            "id": workspace_id,
            "owner_user_id": "owner-1",
            "sandbox_id": "sandbox-1",
            "workspace_path": "/workspace",
        }
    )
    sandbox_repo = SimpleNamespace(
        get_by_id=lambda sandbox_id: {
            "id": sandbox_id,
            "owner_user_id": "owner-1",
            "provider_name": "daytona",
            "provider_env_id": "instance-1",
            "config": {},
        }
    )
    lease_repo = SimpleNamespace(
        get=lambda _lease_id: (_ for _ in ()).throw(AssertionError("thread sandbox status must not read legacy lease id")),
        find_by_instance=lambda *, provider_name, instance_id: {
            "lease_id": "lease-1",
            "provider_name": provider_name,
            "current_instance_id": instance_id,
            "desired_state": "running",
            "observed_state": "running",
            "version": 3,
            "last_error": None,
            "created_at": "2026-04-12T00:00:00Z",
            "updated_at": "2026-04-12T00:01:00Z",
            "_instance": {
                "instance_id": instance_id,
                "status": "running",
                "created_at": "2026-04-12T00:00:10Z",
            },
        },
    )

    result = await get_sandbox_status_from_repos(thread_repo, workspace_repo, sandbox_repo, lease_repo, "thread-1")

    assert result == {
        "thread_id": "thread-1",
        "provider_name": "daytona",
        "desired_state": "running",
        "observed_state": "running",
        "version": 3,
        "last_error": None,
        "instance": {
            "instance_id": "instance-1",
            "state": "running",
            "started_at": "2026-04-12T00:00:10Z",
        },
        "created_at": "2026-04-12T00:00:00Z",
        "updated_at": "2026-04-12T00:01:00Z",
    }
