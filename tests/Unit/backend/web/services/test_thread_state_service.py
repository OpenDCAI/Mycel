from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.threads.state import get_sandbox_info, get_sandbox_status_from_repos


def test_sandbox_info_does_not_expose_terminal_or_session_identity() -> None:
    thread_repo = SimpleNamespace(
        get_by_id=lambda thread_id: {
            "id": thread_id,
            "owner_user_id": "owner-1",
            "agent_user_id": "agent-user-1",
            "current_workspace_id": "workspace-1",
        }
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=thread_repo,
            threads_runtime_state=SimpleNamespace(thread_repo=thread_repo),
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
            sandbox_runtime_repo=SimpleNamespace(
                get=lambda _sandbox_runtime_id: (_ for _ in ()).throw(
                    AssertionError("sandbox info should not read removed sandbox runtime id")
                ),
                find_by_instance=lambda *, provider_name, instance_id: {
                    "lease_" + "id": "runtime-1",
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
async def test_sandbox_status_resolves_runtime_from_provider_env_not_config() -> None:
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
    sandbox_runtime_repo = SimpleNamespace(
        get=lambda _sandbox_runtime_id: (_ for _ in ()).throw(
            AssertionError("thread sandbox status must not read removed sandbox runtime id")
        ),
        find_by_instance=lambda *, provider_name, instance_id: {
            "lease_" + "id": "runtime-1",
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

    result = await get_sandbox_status_from_repos(
        thread_repo,
        workspace_repo,
        sandbox_repo,
        sandbox_runtime_repo,
        "thread-1",
    )

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
