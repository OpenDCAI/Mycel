from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.web.core.dependencies import get_app, get_current_user_id
from backend.web.models.requests import CreateThreadRequest
from backend.web.routers import threads as threads_router
from backend.web.services import thread_launch_config_service
from sandbox.recipes import default_recipe_snapshot, normalize_recipe_snapshot
from storage.contracts import UserRow, UserType


class _FakeUserRepo:
    def __init__(self) -> None:
        self._users = {
            "member-1": UserRow(
                id="member-1",
                type=UserType.AGENT,
                display_name="Toad",
                owner_user_id="owner-1",
                agent_config_id="cfg-1",
                avatar="avatars/member-1.png",
                created_at=1.0,
            ),
            "member-2": UserRow(
                id="member-2",
                type=UserType.AGENT,
                display_name="Dryad",
                owner_user_id="owner-2",
                agent_config_id="cfg-2",
                avatar="avatars/member-2.png",
                created_at=2.0,
            ),
        }
        self._seq = {"member-1": 0, "member-2": 0}

    def get_by_id(self, user_id: str):
        return self._users.get(user_id)

    def increment_thread_seq(self, user_id: str) -> int:
        self._seq[user_id] += 1
        return self._seq[user_id]


class _FakeThreadRepo:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    def get_default_thread(self, agent_user_id: str):
        for row in self.rows.values():
            if row["agent_user_id"] == agent_user_id and row["is_main"]:
                return {"id": row["thread_id"], **row}
        return None

    def get_next_branch_index(self, agent_user_id: str) -> int:
        indices = [row["branch_index"] for row in self.rows.values() if row["agent_user_id"] == agent_user_id]
        return max(indices, default=0) + 1

    def create(self, **kwargs):
        self.rows[kwargs["thread_id"]] = dict(kwargs)

    def list_by_agent_user(self, agent_user_id: str):
        return [{"id": thread_id, **row} for thread_id, row in self.rows.items() if row["agent_user_id"] == agent_user_id]


class _FakeThreadLaunchPrefRepo:
    def __init__(self) -> None:
        self.confirmed: list[tuple[str, str, dict[str, object]]] = []
        self.successful: list[tuple[str, str, dict[str, object]]] = []

    def save_confirmed(self, owner_user_id: str, agent_user_id: str, config: dict[str, object]) -> None:
        self.confirmed.append((owner_user_id, agent_user_id, config))

    def save_successful(self, owner_user_id: str, agent_user_id: str, config: dict[str, object]) -> None:
        self.successful.append((owner_user_id, agent_user_id, config))


def _make_threads_app():
    return SimpleNamespace(
        state=SimpleNamespace(
            user_repo=_FakeUserRepo(),
            thread_repo=_FakeThreadRepo(),
            thread_launch_pref_repo=_FakeThreadLaunchPrefRepo(),
            thread_sandbox={},
            thread_cwd={},
        )
    )


def _route_test_app(app_state: object) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(threads_router.router)
    test_app.dependency_overrides[get_current_user_id] = lambda: "owner-1"
    test_app.dependency_overrides[get_app] = lambda: app_state
    return test_app


def _require_thread_result(result: dict[str, object] | threads_router.JSONResponse) -> dict[str, object]:
    assert not isinstance(result, threads_router.JSONResponse)
    return result


def _recipe_library_entry(provider_type: str) -> dict[str, object]:
    recipe = default_recipe_snapshot(provider_type)
    return {
        **recipe,
        "type": "recipe",
        "available": True,
        "created_at": 0,
        "updated_at": 0,
    }


def test_save_last_confirmed_config_normalizes_payload() -> None:
    app = _make_threads_app()

    thread_launch_config_service.save_last_confirmed_config(
        app=app,
        owner_user_id="owner-1",
        agent_user_id="member-1",
        payload={
            "create_mode": "wat",
            "provider_config": "  local  ",
            "recipe": "nope",
            "lease_id": "  ",
            "model": "  gpt-5.4-mini  ",
            "workspace": "  /tmp/demo  ",
        },
    )

    assert app.state.thread_launch_pref_repo.confirmed == [
        (
            "owner-1",
            "member-1",
            {
                "create_mode": "new",
                "provider_config": "local",
                "recipe": None,
                "lease_id": None,
                "model": "gpt-5.4-mini",
                "workspace": "/tmp/demo",
            },
        )
    ]


def test_build_existing_launch_config_uses_canonical_shape() -> None:
    config = thread_launch_config_service.build_existing_launch_config(
        lease={
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "recipe": {"id": "daytona:recipe-1"},
        },
        model="gpt-5.4",
        workspace="/workspace/reused",
    )

    assert config == {
        "create_mode": "existing",
        "provider_config": "daytona_selfhost",
        "recipe": {"id": "daytona:recipe-1"},
        "lease_id": "lease-1",
        "model": "gpt-5.4",
        "workspace": "/workspace/reused",
    }


def test_build_new_launch_config_normalizes_recipe_snapshot() -> None:
    config = thread_launch_config_service.build_new_launch_config(
        provider_config="local",
        recipe={
            "id": "local:custom",
            "name": "Custom Local",
            "provider_type": "local",
            "features": {"lark_cli": True},
        },
        model="gpt-5.4-mini",
        workspace="/tmp/custom",
    )

    assert config == {
        "create_mode": "new",
        "provider_config": "local",
        "recipe": normalize_recipe_snapshot(
            "local",
            {
                "id": "local:custom",
                "name": "Custom Local",
                "provider_type": "local",
                "features": {"lark_cli": True},
            },
        ),
        "lease_id": None,
        "model": "gpt-5.4-mini",
        "workspace": "/tmp/custom",
    }


def test_resolve_default_config_prefers_last_successful_over_last_confirmed() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_launch_pref_repo=SimpleNamespace(
                get=lambda _owner_user_id, _agent_user_id: {
                    "last_successful": {
                        "create_mode": "existing",
                        "provider_config": "local",
                        "recipe": {"id": "stale"},
                        "lease_id": "lease-1",
                        "model": "gpt-5.4",
                        "workspace": "/workspace/stale",
                    },
                    "last_confirmed": {
                        "create_mode": "new",
                        "provider_config": "local",
                        "recipe": default_recipe_snapshot("local"),
                        "lease_id": None,
                        "model": "gpt-4.1",
                        "workspace": "/tmp/draft",
                    },
                }
            ),
            thread_repo=_FakeThreadRepo(),
            user_repo=SimpleNamespace(),
            recipe_repo=object(),
        )
    )

    with (
        patch.object(
            thread_launch_config_service.sandbox_service,
            "list_user_leases",
            return_value=[
                {
                    "lease_id": "lease-1",
                    "provider_name": "local",
                    "recipe": default_recipe_snapshot("local"),
                    "cwd": "/workspace/reused",
                    "thread_ids": [],
                }
            ],
        ),
        patch.object(
            thread_launch_config_service.sandbox_service,
            "available_sandbox_types",
            return_value=[{"name": "local", "available": True}],
        ),
        patch.object(
            thread_launch_config_service,
            "list_library",
            return_value=[_recipe_library_entry("local")],
        ),
    ):
        result = thread_launch_config_service.resolve_default_config(
            app=app,
            owner_user_id="owner-1",
            agent_user_id="member-1",
        )

    assert result == {
        "source": "last_successful",
        "config": {
            "create_mode": "existing",
            "provider_config": "local",
            "recipe": default_recipe_snapshot("local"),
            "lease_id": "lease-1",
            "model": "gpt-5.4",
            "workspace": "/workspace/reused",
        },
    }


def test_resolve_default_config_skips_invalid_successful_and_uses_confirmed() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_launch_pref_repo=SimpleNamespace(
                get=lambda _owner_user_id, _agent_user_id: {
                    "last_successful": {
                        "create_mode": "existing",
                        "provider_config": "local",
                        "recipe": None,
                        "lease_id": "missing-lease",
                        "model": "gpt-5.4",
                        "workspace": "/workspace/missing",
                    },
                    "last_confirmed": {
                        "create_mode": "new",
                        "provider_config": "local",
                        "recipe": default_recipe_snapshot("local"),
                        "lease_id": None,
                        "model": "gpt-4.1",
                        "workspace": "/tmp/draft",
                    },
                }
            ),
            thread_repo=_FakeThreadRepo(),
            user_repo=SimpleNamespace(),
            recipe_repo=object(),
        )
    )

    with (
        patch.object(
            thread_launch_config_service.sandbox_service,
            "list_user_leases",
            return_value=[],
        ),
        patch.object(
            thread_launch_config_service.sandbox_service,
            "available_sandbox_types",
            return_value=[{"name": "local", "available": True}],
        ),
        patch.object(
            thread_launch_config_service,
            "list_library",
            return_value=[_recipe_library_entry("local")],
        ),
    ):
        result = thread_launch_config_service.resolve_default_config(
            app=app,
            owner_user_id="owner-1",
            agent_user_id="member-1",
        )

    assert result == {
        "source": "last_confirmed",
        "config": {
            "create_mode": "new",
            "provider_config": "local",
            "recipe": default_recipe_snapshot("local"),
            "lease_id": None,
            "model": "gpt-4.1",
            "workspace": "/tmp/draft",
        },
    }


def test_find_owned_agent_returns_none_for_foreign_agent() -> None:
    app = _make_threads_app()

    result = threads_router._find_owned_agent(app, "member-2", "owner-1")

    assert result is None


def test_require_owned_agent_raises_for_foreign_agent() -> None:
    app = _make_threads_app()

    with pytest.raises(threads_router.HTTPException) as excinfo:
        threads_router._require_owned_agent(app, "member-2", "owner-1")

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "Not authorized"


@pytest.mark.asyncio
async def test_create_thread_persists_existing_lease_successful_config() -> None:
    app = _make_threads_app()
    payload = CreateThreadRequest.model_validate(
        {
            "agent_user_id": "member-1",
            "lease_id": "lease-1",
            "model": "gpt-5.4",
            "cwd": "/workspace/requested",
        }
    )

    with (
        patch.object(threads_router, "_validate_sandbox_provider_gate", return_value=None),
        patch.object(threads_router, "_validate_mount_capability_gate", AsyncMock(return_value=None)),
        patch.object(threads_router, "_invalidate_resource_overview_cache", return_value=None),
        patch.object(
            threads_router.sandbox_service,
            "list_user_leases",
            return_value=[
                {
                    "lease_id": "lease-1",
                    "provider_name": "daytona_selfhost",
                    "recipe": {"id": "daytona:recipe-1"},
                }
            ],
        ),
        patch.object(threads_router, "bind_thread_to_existing_lease", return_value="/workspace/reused"),
        patch.object(threads_router, "save_last_successful_config", return_value=None) as save_successful,
    ):
        _require_thread_result(await threads_router.create_thread(payload, "owner-1", app))

    save_successful.assert_called_once_with(
        app,
        "owner-1",
        "member-1",
        {
            "create_mode": "existing",
            "provider_config": "daytona_selfhost",
            "recipe": {"id": "daytona:recipe-1"},
            "lease_id": "lease-1",
            "model": "gpt-5.4",
            "workspace": "/workspace/reused",
        },
    )


@pytest.mark.asyncio
async def test_resolve_main_thread_uses_owned_agent_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _make_threads_app()
    payload = threads_router.ResolveMainThreadRequest(agent_user_id="member-2")
    calls: list[tuple[object, str, str]] = []

    def _fake_find_owned_agent(app_obj, member_id: str, owner_user_id: str):
        calls.append((app_obj, member_id, owner_user_id))
        return None

    monkeypatch.setattr(threads_router, "_find_owned_agent", _fake_find_owned_agent)

    result = await threads_router.resolve_main_thread(payload, "owner-1", app)

    assert result == {
        "agent_user_id": "member-2",
        "default_thread_id": None,
        "thread": None,
    }
    assert calls == [(app, "member-2", "owner-1")]


@pytest.mark.asyncio
async def test_get_default_thread_config_uses_strict_agent_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _make_threads_app()
    calls: list[tuple[object, str, str]] = []

    def _fake_require_owned_agent(app_obj, member_id: str, owner_user_id: str):
        calls.append((app_obj, member_id, owner_user_id))
        raise threads_router.HTTPException(403, "Not authorized")

    monkeypatch.setattr(threads_router, "_require_owned_agent", _fake_require_owned_agent)

    with pytest.raises(threads_router.HTTPException) as excinfo:
        await threads_router.get_default_thread_config("member-2", "owner-1", app)

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "Not authorized"
    assert calls == [(app, "member-2", "owner-1")]


@pytest.mark.asyncio
async def test_save_default_thread_config_uses_strict_agent_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _make_threads_app()
    payload = threads_router.SaveThreadLaunchConfigRequest(
        agent_user_id="member-2",
        create_mode="new",
        provider_config="local",
        recipe=None,
        lease_id=None,
        model="gpt-5.4-mini",
        workspace="/tmp/demo",
    )
    calls: list[tuple[object, str, str]] = []

    def _fake_require_owned_agent(app_obj, member_id: str, owner_user_id: str):
        calls.append((app_obj, member_id, owner_user_id))
        raise threads_router.HTTPException(403, "Not authorized")

    monkeypatch.setattr(threads_router, "_require_owned_agent", _fake_require_owned_agent)

    with pytest.raises(threads_router.HTTPException) as excinfo:
        await threads_router.save_default_thread_config(payload, "owner-1", app)

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "Not authorized"
    assert calls == [(app, "member-2", "owner-1")]


def test_get_default_thread_config_route_rejects_unowned_agent() -> None:
    app = _make_threads_app()

    with TestClient(_route_test_app(app)) as client:
        response = client.get("/api/threads/default-config", params={"agent_user_id": "member-2"})

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized"}


def test_get_default_thread_config_route_uses_owner_and_agent_user_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _make_threads_app()
    calls: list[tuple[object, str, str]] = []
    monkeypatch.setattr(
        threads_router,
        "resolve_default_config",
        lambda app_obj, owner_user_id, agent_user_id: (
            calls.append((app_obj, owner_user_id, agent_user_id))
            or {"source": "last_successful", "config": {"create_mode": "existing", "provider_config": "local"}}
        ),
    )

    with TestClient(_route_test_app(app)) as client:
        response = client.get("/api/threads/default-config", params={"agent_user_id": "member-1"})

    assert response.status_code == 200
    assert response.json() == {"source": "last_successful", "config": {"create_mode": "existing", "provider_config": "local"}}
    assert calls == [(app, "owner-1", "member-1")]


def test_save_default_thread_config_route_persists_confirmed_agent_user_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _make_threads_app()
    calls: list[tuple[object, str, str, dict[str, object]]] = []
    monkeypatch.setattr(
        threads_router,
        "save_last_confirmed_config",
        lambda app_obj, owner_user_id, agent_user_id, payload: calls.append((app_obj, owner_user_id, agent_user_id, payload)),
    )

    with TestClient(_route_test_app(app)) as client:
        response = client.post(
            "/api/threads/default-config",
            json={
                "agent_user_id": "member-1",
                "create_mode": "new",
                "provider_config": "local",
                "recipe": None,
                "lease_id": None,
                "model": "gpt-5.4-mini",
                "workspace": "/tmp/demo",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert calls == [
        (
            app,
            "owner-1",
            "member-1",
            {
                "agent_user_id": "member-1",
                "create_mode": "new",
                "provider_config": "local",
                "recipe": None,
                "lease_id": None,
                "model": "gpt-5.4-mini",
                "workspace": "/tmp/demo",
            },
        )
    ]


@pytest.mark.asyncio
async def test_create_thread_persists_new_launch_successful_config() -> None:
    app = _make_threads_app()
    payload = CreateThreadRequest.model_validate(
        {
            "agent_user_id": "member-1",
            "model": "gpt-5.4-mini",
            "cwd": "/tmp/fresh-local-thread",
        }
    )

    with (
        patch.object(threads_router, "_validate_sandbox_provider_gate", return_value=None),
        patch.object(threads_router, "_validate_mount_capability_gate", AsyncMock(return_value=None)),
        patch.object(threads_router, "_create_thread_sandbox_resources", return_value=None),
        patch.object(threads_router, "_invalidate_resource_overview_cache", return_value=None),
        patch.object(threads_router, "save_last_successful_config", return_value=None) as save_successful,
    ):
        result = _require_thread_result(await threads_router.create_thread(payload, "owner-1", app))

    save_successful.assert_called_once_with(
        app,
        "owner-1",
        "member-1",
        {
            "create_mode": "new",
            "provider_config": "local",
            "recipe": default_recipe_snapshot("local"),
            "lease_id": None,
            "model": "gpt-5.4-mini",
            "workspace": "/tmp/fresh-local-thread",
        },
    )
    assert app.state.thread_cwd[result["thread_id"]] == "/tmp/fresh-local-thread"
