from __future__ import annotations

import json
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
            "agent-user-1": UserRow(
                id="agent-user-1",
                type=UserType.AGENT,
                display_name="Toad",
                owner_user_id="owner-1",
                agent_config_id="cfg-1",
                avatar="avatars/agent-user-1.png",
                created_at=1.0,
            ),
            "agent-user-2": UserRow(
                id="agent-user-2",
                type=UserType.AGENT,
                display_name="Dryad",
                owner_user_id="owner-2",
                agent_config_id="cfg-2",
                avatar="avatars/agent-user-2.png",
                created_at=2.0,
            ),
        }
        self._seq = {"agent-user-1": 0, "agent-user-2": 0}

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


class _FakeRecipeRepo:
    def __init__(self) -> None:
        local = default_recipe_snapshot("local")
        self.rows: dict[tuple[str, str], dict[str, object]] = {
            ("owner-1", str(local["id"])): {
                "owner_user_id": "owner-1",
                "recipe_id": local["id"],
                "kind": "custom",
                "provider_type": "local",
                "data": local,
                "created_at": 0,
                "updated_at": 0,
            }
        }

    def get(self, owner_user_id: str, recipe_id: str):
        return self.rows.get((owner_user_id, recipe_id))

    def list_by_owner(self, owner_user_id: str):
        return [row for (owner, _recipe_id), row in self.rows.items() if owner == owner_user_id]


class _FakeWorkspaceRepo:
    def __init__(self) -> None:
        self.created: list[object] = []
        self.by_id: dict[str, object] = {}
        self.by_sandbox_id: dict[str, list[object]] = {}

    def get_by_id(self, workspace_id: str):
        return self.by_id.get(workspace_id)

    def list_by_sandbox_id(self, sandbox_id: str):
        return list(self.by_sandbox_id.get(sandbox_id, []))

    def create(self, row) -> None:
        self.created.append(row)
        self.by_id[row.id] = row
        self.by_sandbox_id.setdefault(row.sandbox_id, []).append(row)


class _FakeSandboxRepo:
    def __init__(self) -> None:
        self.created: list[object] = []
        self.by_id: dict[str, object] = {}

    def get_by_id(self, sandbox_id: str):
        return self.by_id.get(sandbox_id)

    def create(self, row) -> None:
        self.created.append(row)
        self.by_id[row.id] = row


class _FakeLeaseRepo:
    def __init__(self, row: dict[str, object] | None = None) -> None:
        self._row = row
        self.instance_queries: list[tuple[str, str]] = []

    def find_by_instance(self, *, provider_name: str, instance_id: str):
        self.instance_queries.append((provider_name, instance_id))
        if self._row is None:
            return None
        row_provider = str(self._row.get("provider_name") or "").strip()
        row_instance = str(self._row.get("provider_env_id") or self._row.get("current_instance_id") or "").strip()
        return self._row if row_provider == provider_name and row_instance == instance_id else None


def _make_threads_app():
    return SimpleNamespace(
        state=SimpleNamespace(
            user_repo=_FakeUserRepo(),
            thread_repo=_FakeThreadRepo(),
            recipe_repo=_FakeRecipeRepo(),
            workspace_repo=_FakeWorkspaceRepo(),
            sandbox_repo=_FakeSandboxRepo(),
            lease_repo=_FakeLeaseRepo(),
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
        "type": "sandbox-template",
        "available": True,
        "created_at": 0,
        "updated_at": 0,
    }


def test_launch_config_service_does_not_expose_lease_shell_builder() -> None:
    assert not hasattr(thread_launch_config_service, "build_existing_launch_config")


def test_build_new_launch_config_uses_sandbox_template_id() -> None:
    config = thread_launch_config_service.build_new_launch_config(
        provider_config="local",
        sandbox_template_id="local:custom",
        model="gpt-5.4-mini",
        workspace="/tmp/custom",
    )

    assert config == {
        "create_mode": "new",
        "provider_config": "local",
        "sandbox_template_id": "local:custom",
        "existing_sandbox_id": None,
        "model": "gpt-5.4-mini",
        "workspace": "/tmp/custom",
    }


def test_resolve_default_config_derives_existing_from_workspace_backed_current_workspace_id() -> None:
    thread_repo = _FakeThreadRepo()
    thread_repo.rows["agent-user-1-1"] = {
        "thread_id": "agent-user-1-1",
        "agent_user_id": "agent-user-1",
        "current_workspace_id": "ws-2",
        "is_main": True,
        "branch_index": 0,
        "created_at": 2.0,
    }
    workspace_repo = _FakeWorkspaceRepo()
    workspace_repo.by_id["ws-2"] = SimpleNamespace(
        id="ws-2",
        sandbox_id="sandbox-2",
        owner_user_id="owner-1",
        workspace_path="/workspace/right",
        name=None,
        created_at=2.0,
        updated_at=2.0,
    )
    sandbox_repo = _FakeSandboxRepo()
    sandbox_repo.by_id["sandbox-2"] = SimpleNamespace(
        id="sandbox-2",
        owner_user_id="owner-1",
        provider_name="agent_bay",
        provider_env_id="provider-env-2",
        sandbox_template_id="daytona:default",
        desired_state="running",
        observed_state="running",
        status="ready",
        observed_at=2.0,
        last_error=None,
        config={},
        created_at=2.0,
        updated_at=2.0,
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=thread_repo,
            user_repo=SimpleNamespace(),
            recipe_repo=object(),
            workspace_repo=workspace_repo,
            sandbox_repo=sandbox_repo,
        )
    )

    with (
        patch.object(
            thread_launch_config_service.sandbox_service,
            "available_sandbox_types",
            return_value=[
                {"name": "local", "available": True},
                {"name": "daytona_selfhost", "available": True},
            ],
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
            agent_user_id="agent-user-1",
        )

    assert result == {
        "source": "derived",
        "config": {
            "create_mode": "existing",
            "provider_config": "agent_bay",
            "sandbox_template": default_recipe_snapshot("daytona"),
            "existing_sandbox_id": "sandbox-2",
            "model": None,
            "workspace": "/workspace/right",
        },
    }


def test_resolve_default_config_uses_sandbox_template_id_over_lease_recipe_for_workspace_backed_existing_mode() -> None:
    thread_repo = _FakeThreadRepo()
    thread_repo.rows["agent-user-1-1"] = {
        "thread_id": "agent-user-1-1",
        "agent_user_id": "agent-user-1",
        "current_workspace_id": "ws-3",
        "is_main": True,
        "branch_index": 0,
        "created_at": 3.0,
    }
    workspace_repo = _FakeWorkspaceRepo()
    workspace_repo.by_id["ws-3"] = SimpleNamespace(
        id="ws-3",
        sandbox_id="sandbox-3",
        owner_user_id="owner-1",
        workspace_path="/workspace/template-from-sandbox",
        name=None,
        created_at=3.0,
        updated_at=3.0,
    )
    sandbox_repo = _FakeSandboxRepo()
    sandbox_repo.by_id["sandbox-3"] = SimpleNamespace(
        id="sandbox-3",
        owner_user_id="owner-1",
        provider_name="daytona_selfhost",
        provider_env_id="provider-env-3",
        sandbox_template_id="daytona:custom:lark",
        desired_state="running",
        observed_state="running",
        status="ready",
        observed_at=3.0,
        last_error=None,
        config={},
        created_at=3.0,
        updated_at=3.0,
    )
    recipe_repo = _FakeRecipeRepo()
    recipe_repo.rows[("owner-1", "daytona:custom:lark")] = {
        "owner_user_id": "owner-1",
        "recipe_id": "daytona:custom:lark",
        "kind": "custom",
        "provider_type": "daytona",
        "data": {
            "id": "daytona:custom:lark",
            "name": "Daytona Custom Lark",
            "desc": "custom",
            "provider_name": "daytona_selfhost",
            "provider_type": "daytona",
            "features": {"lark_cli": True},
            "builtin": False,
        },
        "created_at": 0,
        "updated_at": 0,
    }
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=thread_repo,
            user_repo=SimpleNamespace(),
            recipe_repo=recipe_repo,
            workspace_repo=workspace_repo,
            sandbox_repo=sandbox_repo,
        )
    )

    with (
        patch.object(
            thread_launch_config_service.sandbox_service,
            "available_sandbox_types",
            return_value=[{"name": "daytona_selfhost", "available": True}],
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
            agent_user_id="agent-user-1",
        )

    assert result == {
        "source": "derived",
        "config": {
            "create_mode": "existing",
            "provider_config": "daytona_selfhost",
            "sandbox_template": normalize_recipe_snapshot(
                "daytona",
                recipe_repo.rows[("owner-1", "daytona:custom:lark")]["data"],
                provider_name="daytona_selfhost",
            ),
            "existing_sandbox_id": "sandbox-3",
            "model": None,
            "workspace": "/workspace/template-from-sandbox",
        },
    }


def test_resolve_default_config_fails_loudly_when_workspace_backed_template_source_is_missing() -> None:
    thread_repo = _FakeThreadRepo()
    thread_repo.rows["agent-user-1-1"] = {
        "thread_id": "agent-user-1-1",
        "agent_user_id": "agent-user-1",
        "current_workspace_id": "ws-missing-template",
        "is_main": True,
        "branch_index": 0,
        "created_at": 4.0,
    }
    workspace_repo = _FakeWorkspaceRepo()
    workspace_repo.by_id["ws-missing-template"] = SimpleNamespace(
        id="ws-missing-template",
        sandbox_id="sandbox-missing-template",
        owner_user_id="owner-1",
        workspace_path="/workspace/missing-template",
        name=None,
        created_at=4.0,
        updated_at=4.0,
    )
    sandbox_repo = _FakeSandboxRepo()
    sandbox_repo.by_id["sandbox-missing-template"] = SimpleNamespace(
        id="sandbox-missing-template",
        owner_user_id="owner-1",
        provider_name="daytona_selfhost",
        provider_env_id="provider-env-4",
        sandbox_template_id="daytona:custom:missing",
        desired_state="running",
        observed_state="running",
        status="ready",
        observed_at=4.0,
        last_error=None,
        config={},
        created_at=4.0,
        updated_at=4.0,
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=thread_repo,
            user_repo=SimpleNamespace(),
            recipe_repo=_FakeRecipeRepo(),
            workspace_repo=workspace_repo,
            sandbox_repo=sandbox_repo,
        )
    )

    with (
        patch.object(
            thread_launch_config_service.sandbox_service,
            "available_sandbox_types",
            return_value=[{"name": "daytona_selfhost", "available": True}],
        ),
        patch.object(
            thread_launch_config_service,
            "list_library",
            return_value=[_recipe_library_entry("local")],
        ),
        pytest.raises(RuntimeError, match="sandbox template not found: daytona:custom:missing"),
    ):
        thread_launch_config_service.resolve_default_config(
            app=app,
            owner_user_id="owner-1",
            agent_user_id="agent-user-1",
        )


def test_resolve_default_config_derives_existing_from_legacy_lease_backed_current_workspace_id() -> None:
    thread_repo = _FakeThreadRepo()
    thread_repo.rows["agent-user-1-1"] = {
        "thread_id": "agent-user-1-1",
        "agent_user_id": "agent-user-1",
        "current_workspace_id": "lease-2",
        "is_main": True,
        "branch_index": 0,
        "created_at": 1.0,
    }
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=thread_repo,
            user_repo=SimpleNamespace(),
            recipe_repo=object(),
            workspace_repo=_FakeWorkspaceRepo(),
            sandbox_repo=_FakeSandboxRepo(),
        )
    )

    with (
        patch.object(
            thread_launch_config_service.sandbox_service,
            "available_sandbox_types",
            return_value=[
                {"name": "local", "available": True},
                {"name": "daytona_selfhost", "available": True},
            ],
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
            agent_user_id="agent-user-1",
        )

    assert result == {
        "source": "derived",
        "config": {
            "create_mode": "new",
            "provider_config": "local",
            "sandbox_template_id": "local:default",
            "sandbox_template": default_recipe_snapshot("local"),
            "existing_sandbox_id": None,
            "model": None,
            "workspace": None,
        },
    }


def test_resolve_default_config_fails_loudly_for_malformed_workspace_bridge() -> None:
    thread_repo = _FakeThreadRepo()
    thread_repo.rows["agent-user-1-1"] = {
        "thread_id": "agent-user-1-1",
        "agent_user_id": "agent-user-1",
        "current_workspace_id": "ws-bad",
        "is_main": True,
        "branch_index": 0,
        "created_at": 3.0,
    }
    workspace_repo = _FakeWorkspaceRepo()
    workspace_repo.by_id["ws-bad"] = SimpleNamespace(
        id="ws-bad",
        sandbox_id="",
        owner_user_id="owner-1",
        workspace_path="/workspace/bad",
        name=None,
        created_at=3.0,
        updated_at=3.0,
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=thread_repo,
            user_repo=SimpleNamespace(),
            recipe_repo=object(),
            workspace_repo=workspace_repo,
        )
    )

    with (
        patch.object(thread_launch_config_service.sandbox_service, "available_sandbox_types", return_value=[]),
        patch.object(thread_launch_config_service, "list_library", return_value=[]),
        pytest.raises(RuntimeError, match="workspace.sandbox_id is required"),
    ):
        thread_launch_config_service.resolve_default_config(
            app=app,
            owner_user_id="owner-1",
            agent_user_id="agent-user-1",
        )


def test_resolve_default_config_falls_back_to_new_default_when_thread_workspace_bridge_is_missing() -> None:
    thread_repo = _FakeThreadRepo()
    thread_repo.rows["agent-user-1-1"] = {
        "thread_id": "agent-user-1-1",
        "agent_user_id": "agent-user-1",
        "current_workspace_id": "missing-lease",
        "is_main": True,
        "branch_index": 0,
    }
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=thread_repo,
            user_repo=SimpleNamespace(),
            recipe_repo=object(),
            workspace_repo=_FakeWorkspaceRepo(),
        )
    )

    with (
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
            agent_user_id="agent-user-1",
        )

    assert result == {
        "source": "derived",
        "config": {
            "create_mode": "new",
            "provider_config": "local",
            "sandbox_template_id": "local:default",
            "sandbox_template": default_recipe_snapshot("local"),
            "existing_sandbox_id": None,
            "model": None,
            "workspace": None,
        },
    }


def test_find_owned_agent_returns_none_for_foreign_agent() -> None:
    app = _make_threads_app()

    result = threads_router._find_owned_agent(app, "agent-user-2", "owner-1")

    assert result is None


def test_require_owned_agent_raises_for_foreign_agent() -> None:
    app = _make_threads_app()

    with pytest.raises(threads_router.HTTPException) as excinfo:
        threads_router._require_owned_agent(app, "agent-user-2", "owner-1")

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "Not authorized"


@pytest.mark.asyncio
async def test_create_thread_existing_lease_binds_without_launch_config_save() -> None:
    app = _make_threads_app()
    app.state.sandbox_repo.by_id["sandbox-1"] = {
        "id": "sandbox-1",
        "owner_user_id": "owner-1",
        "provider_name": "daytona_selfhost",
        "provider_env_id": "instance-1",
        "config": {},
    }
    app.state.lease_repo = _FakeLeaseRepo(
        {
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "provider_env_id": "instance-1",
            "recipe": {"id": "daytona:recipe-1"},
        }
    )
    payload = CreateThreadRequest.model_validate(
        {
            "agent_user_id": "agent-user-1",
            "existing_sandbox_id": "sandbox-1",
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
            "resolve_owned_lease",
            return_value={
                "lease_id": "lease-1",
                "provider_name": "daytona_selfhost",
                "recipe": {"id": "daytona:recipe-1"},
            },
        ),
        patch.object(
            threads_router,
            "bind_thread_to_existing_sandbox",
            return_value=(
                "/workspace/reused",
                {
                    "lease_id": "lease-1",
                    "provider_name": "daytona_selfhost",
                    "recipe": {"id": "daytona:recipe-1"},
                },
            ),
        ),
    ):
        result = _require_thread_result(await threads_router.create_thread(payload, "owner-1", app))

    assert app.state.thread_cwd[result["thread_id"]] == "/workspace/reused"


@pytest.mark.asyncio
async def test_resolve_main_thread_uses_owned_agent_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _make_threads_app()
    payload = threads_router.ResolveMainThreadRequest(agent_user_id="agent-user-2")
    calls: list[tuple[object, str, str]] = []

    def _fake_find_owned_agent(app_obj, agent_user_id: str, owner_user_id: str):
        calls.append((app_obj, agent_user_id, owner_user_id))
        return None

    monkeypatch.setattr(threads_router, "_find_owned_agent", _fake_find_owned_agent)

    result = await threads_router.resolve_main_thread(payload, "owner-1", app)

    assert result == {
        "agent_user_id": "agent-user-2",
        "default_thread_id": None,
        "thread": None,
    }
    assert calls == [(app, "agent-user-2", "owner-1")]


@pytest.mark.asyncio
async def test_get_default_thread_config_uses_strict_agent_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _make_threads_app()
    calls: list[tuple[object, str, str]] = []

    def _fake_require_owned_agent(app_obj, agent_user_id: str, owner_user_id: str):
        calls.append((app_obj, agent_user_id, owner_user_id))
        raise threads_router.HTTPException(403, "Not authorized")

    monkeypatch.setattr(threads_router, "_require_owned_agent", _fake_require_owned_agent)

    with pytest.raises(threads_router.HTTPException) as excinfo:
        await threads_router.get_default_thread_config("agent-user-2", "owner-1", app)

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "Not authorized"
    assert calls == [(app, "agent-user-2", "owner-1")]


@pytest.mark.asyncio
async def test_get_default_thread_config_runs_sync_repo_work_off_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _make_threads_app()
    to_thread_calls: list[tuple[str, tuple[object, ...]]] = []

    async def _fake_to_thread(fn, *args):
        to_thread_calls.append((fn.__name__, args))
        return fn(*args)

    monkeypatch.setattr(threads_router.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr(threads_router, "_require_owned_agent", lambda app_obj, agent_user_id, owner_user_id: object())
    monkeypatch.setattr(
        threads_router,
        "resolve_default_config",
        lambda app_obj, owner_user_id, agent_user_id: {
            "source": "last_successful",
            "config": {
                "create_mode": "existing",
                "provider_config": "local",
                "existing_sandbox_id": "lease-1",
            },
        },
    )

    result = await threads_router.get_default_thread_config("agent-user-1", "owner-1", app)

    assert result == {
        "source": "last_successful",
        "config": {
            "create_mode": "existing",
            "provider_config": "local",
            "existing_sandbox_id": "lease-1",
        },
    }
    assert to_thread_calls == [("_resolve_default_config_for_owned_agent", (app, "owner-1", "agent-user-1"))]


def test_get_default_thread_config_route_rejects_unowned_agent() -> None:
    app = _make_threads_app()

    with TestClient(_route_test_app(app)) as client:
        response = client.get("/api/threads/default-config", params={"agent_user_id": "agent-user-2"})

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
        response = client.get("/api/threads/default-config", params={"agent_user_id": "agent-user-1"})

    assert response.status_code == 200
    assert response.json() == {
        "source": "last_successful",
        "config": {
            "create_mode": "existing",
            "provider_config": "local",
        },
    }
    assert calls == [(app, "owner-1", "agent-user-1")]


@pytest.mark.asyncio
async def test_create_thread_persists_cwd_without_launch_config_save() -> None:
    app = _make_threads_app()
    payload = CreateThreadRequest.model_validate(
        {
            "agent_user_id": "agent-user-1",
            "model": "gpt-5.4-mini",
            "cwd": "/tmp/fresh-local-thread",
        }
    )

    with (
        patch.object(threads_router, "_validate_sandbox_provider_gate", return_value=None),
        patch.object(threads_router, "_validate_mount_capability_gate", AsyncMock(return_value=None)),
        patch.object(threads_router, "_validate_sandbox_quota_gate", return_value=None),
        patch.object(threads_router, "_create_thread_sandbox_resources", return_value=None),
        patch.object(threads_router, "_invalidate_resource_overview_cache", return_value=None),
    ):
        result = _require_thread_result(await threads_router.create_thread(payload, "owner-1", app))

    assert app.state.thread_cwd[result["thread_id"]] == "/tmp/fresh-local-thread"


@pytest.mark.asyncio
async def test_create_thread_carries_recipe_snapshot_into_resources_without_launch_config_save() -> None:
    app = _make_threads_app()
    repo_recipe = {
        "id": "local:custom:lark",
        "name": "Repo Local With Lark",
        "provider_name": "local",
        "provider_type": "local",
        "features": {"lark_cli": True},
        "configurable_features": {"lark_cli": True},
        "feature_options": [{"key": "lark_cli", "name": "Lark CLI", "description": "Install Lark CLI"}],
        "builtin": False,
    }
    app.state.recipe_repo.rows[("owner-1", "local:custom:lark")] = {
        "owner_user_id": "owner-1",
        "recipe_id": "local:custom:lark",
        "kind": "custom",
        "provider_type": "local",
        "data": repo_recipe,
        "created_at": 0,
        "updated_at": 0,
    }
    payload = CreateThreadRequest.model_validate(
        {
            "agent_user_id": "agent-user-1",
            "model": "gpt-5.4-mini",
            "sandbox": "local",
            "sandbox_template_id": "local:custom:lark",
        }
    )
    normalized_recipe = normalize_recipe_snapshot("local", repo_recipe)

    with (
        patch.object(threads_router, "_validate_sandbox_provider_gate", return_value=None),
        patch.object(threads_router, "_validate_mount_capability_gate", AsyncMock(return_value=None)),
        patch.object(threads_router, "_validate_sandbox_quota_gate", return_value=None),
        patch.object(threads_router, "_create_thread_sandbox_resources", return_value=None) as create_resources,
        patch.object(threads_router, "_invalidate_resource_overview_cache", return_value=None),
    ):
        result = _require_thread_result(await threads_router.create_thread(payload, "owner-1", app))

    create_resources.assert_called_once_with(
        result["thread_id"],
        "local",
        normalized_recipe,
        None,
        workspace_repo=app.state.workspace_repo,
        owner_user_id="owner-1",
    )


@pytest.mark.asyncio
async def test_create_thread_rejects_unowned_recipe_snapshot() -> None:
    app = _make_threads_app()
    payload = CreateThreadRequest.model_validate(
        {
            "agent_user_id": "agent-user-1",
            "model": "gpt-5.4-mini",
            "sandbox": "local",
            "sandbox_template_id": "local:custom:foreign",
        }
    )

    with (
        patch.object(threads_router, "_validate_sandbox_provider_gate", return_value=None),
        patch.object(threads_router, "_validate_mount_capability_gate", AsyncMock(return_value=None)),
        patch.object(threads_router, "_validate_sandbox_quota_gate", return_value=None),
        patch.object(threads_router, "_create_thread_sandbox_resources", return_value=None) as create_resources,
    ):
        with pytest.raises(threads_router.HTTPException) as excinfo:
            await threads_router.create_thread(payload, "owner-1", app)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Recipe not found"
    create_resources.assert_not_called()


@pytest.mark.asyncio
async def test_create_thread_rejects_new_lease_when_account_resource_limit_is_reached() -> None:
    app = _make_threads_app()
    payload = CreateThreadRequest.model_validate(
        {
            "agent_user_id": "agent-user-1",
            "model": "gpt-5.4-mini",
            "sandbox": "daytona_selfhost",
        }
    )

    def _raise_limit(*_args, **_kwargs):
        raise threads_router.account_resource_service.AccountResourceLimitExceededError(
            {
                "resource": "sandbox",
                "provider_name": "daytona_selfhost",
                "label": "Self-host Daytona",
                "limit": 2,
                "used": 2,
                "remaining": 0,
                "can_create": False,
            }
        )

    with (
        patch.object(threads_router, "_validate_sandbox_provider_gate", return_value=None),
        patch.object(threads_router, "_validate_mount_capability_gate", AsyncMock(return_value=None)),
        patch.object(threads_router.account_resource_service, "assert_can_create_sandbox", side_effect=_raise_limit),
        patch.object(threads_router, "_create_thread_sandbox_resources", return_value=None) as create_resources,
    ):
        result = await threads_router.create_thread(payload, "owner-1", app)

    assert isinstance(result, threads_router.JSONResponse)
    assert result.status_code == 409
    assert json.loads(result.body) == {
        "error": "sandbox_quota_exceeded",
        "message": "Self-host Daytona sandbox quota exceeded",
        "resource": {
            "resource": "sandbox",
            "provider_name": "daytona_selfhost",
            "label": "Self-host Daytona",
            "limit": 2,
            "used": 2,
            "remaining": 0,
            "can_create": False,
        },
    }
    create_resources.assert_not_called()
