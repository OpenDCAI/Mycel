from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.web.routers import sandbox as sandbox_router
from backend.web.services import sandbox_service


def test_sandbox_router_does_not_expose_local_folder_picker() -> None:
    paths = {route.path for route in sandbox_router.router.routes}

    assert "/api/sandbox/pick-folder" not in paths
    removed_owner_route = "/api/sandbox/" + "lease" + "s/mine"
    assert removed_owner_route not in paths


@pytest.mark.asyncio
async def test_list_my_sandboxes_uses_canonical_sandbox_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_list_user_sandboxes(user_id: str, *, thread_repo=None, user_repo=None) -> list[dict[str, object]]:
        seen.update(
            {
                "user_id": user_id,
                "thread_repo": thread_repo,
                "user_repo": user_repo,
            }
        )
        return [{"sandbox_id": "sandbox-1"}]

    thread_repo = SimpleNamespace()
    user_repo = SimpleNamespace()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(thread_repo=thread_repo, user_repo=user_repo)))
    monkeypatch.setattr(sandbox_router.sandbox_service, "list_user_sandboxes", fake_list_user_sandboxes, raising=False)

    result = await sandbox_router.list_my_sandboxes(user_id="owner-1", request=request)

    assert result == {"sandboxes": [{"sandbox_id": "sandbox-1"}]}
    assert seen == {
        "user_id": "owner-1",
        "thread_repo": thread_repo,
        "user_repo": user_repo,
    }


def test_list_user_sandboxes_projects_internal_lease_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    class _MonitorRepo:
        def query_sandboxes(self) -> list[dict[str, object]]:
            return [
                {
                    "lease_id": "lease-1",
                    "sandbox_id": "sandbox-1",
                    "provider_name": "local",
                    "recipe_id": "local:default",
                    "thread_id": "thread-1",
                    "observed_state": "running",
                    "desired_state": "running",
                }
            ]

        def close(self) -> None:
            return None

    thread_repo = SimpleNamespace(
        list_by_owner_user_id=lambda user_id: [{"id": "thread-1", "agent_user_id": "agent-1"}] if user_id == "owner-1" else []
    )
    user_repo = SimpleNamespace(
        list_by_owner_user_id=lambda user_id: (
            [SimpleNamespace(id="agent-1", display_name="Morel", avatar=None)] if user_id == "owner-1" else []
        )
    )
    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda: _MonitorRepo())

    result = sandbox_service.list_user_sandboxes(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
    )

    assert len(result) == 1
    assert "lease_id" not in result[0]
    assert result[0]["sandbox_id"] == "sandbox-1"
    assert result[0]["provider_name"] == "local"
    assert result[0]["thread_ids"] == ["thread-1"]
