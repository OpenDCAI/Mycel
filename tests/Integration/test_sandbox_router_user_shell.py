from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.sandboxes import service as sandbox_service
from backend.web.routers import sandbox as sandbox_router


@pytest.mark.asyncio
async def test_list_my_sandboxes_uses_canonical_sandbox_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_list_user_sandboxes(user_id: str, *, thread_repo=None, user_repo=None, **kwargs) -> list[dict[str, object]]:
        seen.update(
            {
                "user_id": user_id,
                "thread_repo": thread_repo,
                "user_repo": user_repo,
                "kwargs": kwargs,
            }
        )
        return [{"sandbox_id": "sandbox-1"}]

    thread_repo = SimpleNamespace()
    user_repo = SimpleNamespace()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(thread_repo=thread_repo, user_repo=user_repo)))
    monkeypatch.setattr(sandbox_router.user_sandbox_reads, "list_user_sandboxes", fake_list_user_sandboxes, raising=False)

    result = await sandbox_router.list_my_sandboxes(user_id="owner-1", request=request)

    assert result == {"sandboxes": [{"sandbox_id": "sandbox-1"}]}
    assert seen["user_id"] == "owner-1"
    assert seen["thread_repo"] is thread_repo
    assert seen["user_repo"] is user_repo
    assert seen["kwargs"]["make_sandbox_monitor_repo_fn"] is sandbox_router.make_sandbox_monitor_repo
    assert seen["kwargs"]["canonical_owner_threads_fn"] is sandbox_router.canonical_owner_threads
    assert seen["kwargs"]["avatar_url_fn"] is sandbox_router.avatar_url
    assert seen["kwargs"]["is_virtual_thread_id_fn"] is sandbox_router.is_virtual_thread_id


def test_sandbox_runtime_routes_do_not_expose_session_paths() -> None:
    route_paths = {getattr(route, "path", "") for route in sandbox_router.router.routes}

    assert "/api/sandbox/runtimes" in route_paths
    assert "/api/sandbox/runtimes/{runtime_id}/metrics" in route_paths
    assert "/api/sandbox/runtimes/{runtime_id}/pause" in route_paths
    assert "/api/sandbox/runtimes/{runtime_id}/resume" in route_paths
    assert "/api/sandbox/runtimes/{runtime_id}" in route_paths
    assert not any("/sessions" in path for path in route_paths)


@pytest.mark.asyncio
async def test_list_sandbox_types_reports_current_daytona_provider_when_inventory_builds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sandbox_router.sandbox_provider_availability,
        "available_sandbox_types",
        lambda: [
            {"name": "local", "provider": "local", "available": True},
            {"name": "daytona_selfhost", "provider": "daytona", "available": True},
        ],
    )

    result = await sandbox_router.list_sandbox_types()

    assert result["types"] == [
        {"name": "local", "provider": "local", "available": True},
        {"name": "daytona_selfhost", "provider": "daytona", "available": True},
    ]


@pytest.mark.asyncio
async def test_list_sandbox_runtimes_strips_lower_runtime_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sandbox_router, "init_providers_and_managers", lambda: ({}, {"local": object()}))
    monkeypatch.setattr(
        sandbox_router,
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
        sandbox_router.sandbox_runtime_mutations,
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
