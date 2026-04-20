from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from backend.web.routers import sandbox as sandbox_router
from backend.web.services import sandbox_service


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


def test_sandbox_runtime_routes_do_not_expose_session_paths() -> None:
    route_paths = {getattr(route, "path", "") for route in sandbox_router.router.routes}

    assert "/api/sandbox/runtimes" in route_paths
    assert "/api/sandbox/runtimes/{runtime_id}/metrics" in route_paths
    assert "/api/sandbox/runtimes/{runtime_id}/pause" in route_paths
    assert "/api/sandbox/runtimes/{runtime_id}/resume" in route_paths
    assert "/api/sandbox/runtimes/{runtime_id}" in route_paths
    assert not any("/sessions" in path for path in route_paths)


def test_sandbox_runtime_metrics_route_uses_neutral_owner() -> None:
    source = inspect.getsource(sandbox_router)

    assert "sandbox_service.get_runtime_metrics" not in source
    assert "sandbox_runtime_metrics.get_runtime_metrics" in source


@pytest.mark.asyncio
async def test_list_sandbox_runtimes_strips_lower_runtime_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sandbox_router.sandbox_service, "init_providers_and_managers", lambda: ({}, {"local": object()}))
    monkeypatch.setattr(
        sandbox_router.sandbox_service,
        "load_all_sandbox_runtimes",
        lambda _managers: [
            {
                "session_id": "session-1",
                "thread_id": "thread-1",
                "provider": "local",
                "status": "running",
                "lease_" + "id": "lease-1",
                "instance_id": "instance-1",
            }
        ],
    )

    result = await sandbox_router.list_sandbox_runtimes()

    assert "sess" + "ions" not in result
    assert result["runtime_rows"] == [
        {
            "session_id": "session-1",
            "thread_id": "thread-1",
            "provider": "local",
            "status": "running",
            "instance_id": "instance-1",
        }
    ]


@pytest.mark.asyncio
async def test_sandbox_runtime_mutation_response_strips_lower_runtime_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_mutate_sandbox_runtime(**kwargs: object) -> dict[str, object]:
        seen.update(kwargs)
        return {
            "ok": True,
            "action": "pause",
            "session_id": "runtime-1",
            "provider": "local",
            "thread_id": None,
            "lease_" + "id": "lease-1",
            "mode": "manager_runtime",
        }

    monkeypatch.setattr(
        sandbox_router.sandbox_service,
        "mutate_sandbox_runtime",
        fake_mutate_sandbox_runtime,
    )

    result = await sandbox_router.pause_sandbox_runtime("runtime-1")

    assert result == {
        "ok": True,
        "action": "pause",
        "session_id": "runtime-1",
        "provider": "local",
        "thread_id": None,
        "mode": "manager_runtime",
    }
    assert seen["runtime_id"] == "runtime-1"


def test_list_user_sandboxes_projects_internal_runtime_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    class _MonitorRepo:
        def query_sandboxes(self) -> list[dict[str, object]]:
            return [
                {
                    "lease_" + "id": "lease-1",
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
    assert "lease_" + "id" not in result[0]
    assert result[0]["sandbox_id"] == "sandbox-1"
    assert result[0]["provider_name"] == "local"
    assert result[0]["thread_ids"] == ["thread-1"]
