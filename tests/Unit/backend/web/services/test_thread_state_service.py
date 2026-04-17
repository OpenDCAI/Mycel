from __future__ import annotations

from types import SimpleNamespace

from backend.web.services.thread_state_service import get_sandbox_info


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
                    "config": {"legacy_lease_id": "lease-1"},
                }
            ),
            lease_repo=SimpleNamespace(
                get=lambda lease_id: {
                    "lease_id": lease_id,
                    "observed_state": "running",
                    "_instance": {"status": "running", "instance_id": "instance-1"},
                }
            ),
            terminal_repo=SimpleNamespace(
                get_active=lambda _thread_id: (_ for _ in ()).throw(AssertionError("sandbox info should not read terminal rows"))
            ),
        )
    )

    payload = get_sandbox_info(app, "thread-1", "daytona")

    assert payload == {"type": "daytona", "status": "running"}
