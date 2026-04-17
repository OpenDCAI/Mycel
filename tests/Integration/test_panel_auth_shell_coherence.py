from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.models import panel as panel_models
from backend.web.models.panel import PublishAgentRequest, UpdateAgentRequest, UpdateProfileRequest
from backend.web.routers import panel as panel_router
from backend.web.services import agent_user_service, library_service, profile_service
from storage.contracts import UserRow, UserType


def test_panel_router_exposes_agents_routes_not_members_routes():
    route_paths = {(route.path, tuple(sorted(route.methods or []))) for route in panel_router.router.routes}

    assert ("/api/panel/agents", ("GET",)) in route_paths
    assert ("/api/panel/agents/{agent_id}", ("GET",)) in route_paths
    assert ("/api/panel/agents", ("POST",)) in route_paths
    assert ("/api/panel/agents/{agent_id}", ("PUT",)) in route_paths
    assert ("/api/panel/agents/{agent_id}/config", ("PUT",)) in route_paths
    assert ("/api/panel/agents/{agent_id}/publish", ("PUT",)) in route_paths
    assert ("/api/panel/agents/{agent_id}", ("DELETE",)) in route_paths
    assert ("/api/panel/members", ("GET",)) not in route_paths
    assert ("/api/panel/members/{agent_id}", ("GET",)) not in route_paths


def test_panel_models_expose_agent_requests_not_member_or_staff_aliases():
    assert hasattr(panel_models, "AgentConfigPayload")
    assert hasattr(panel_models, "CreateAgentRequest")
    assert hasattr(panel_models, "UpdateAgentRequest")
    assert hasattr(panel_models, "PublishAgentRequest")
    assert not hasattr(panel_models, "MemberConfigPayload")
    assert not hasattr(panel_models, "CreateMemberRequest")
    assert not hasattr(panel_models, "UpdateMemberRequest")
    assert not hasattr(panel_models, "PublishMemberRequest")
    assert not hasattr(panel_models, "StaffConfigPayload")
    assert not hasattr(panel_models, "CreateStaffRequest")
    assert not hasattr(panel_models, "UpdateStaffRequest")
    assert not hasattr(panel_models, "PublishStaffRequest")


@pytest.mark.asyncio
async def test_panel_agents_uses_injected_user_repo_for_owner_scope(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    agent = UserRow(
        id="agent-1",
        type=UserType.AGENT,
        display_name="Toad",
        owner_user_id="user-1",
        agent_config_id="cfg-1",
        created_at=1.0,
    )
    seen: list[str] = []
    fake_repo = SimpleNamespace(
        list_by_owner_user_id=lambda owner_user_id: seen.append(owner_user_id) or [agent],
    )
    fake_agent_config_repo = SimpleNamespace(
        get_config=lambda agent_config_id: {
            "id": agent_config_id,
            "name": "Toad",
            "description": "",
            "tools": ["*"],
            "system_prompt": "hello",
            "status": "draft",
            "version": "0.1.0",
            "runtime": {},
            "mcp": {},
            "meta": {"source": {"marketplace_item_id": "item-1", "installed_version": "1.0.0"}},
            "created_at": 1,
            "updated_at": 2,
        },
        list_rules=lambda _agent_config_id: [],
        list_skills=lambda _agent_config_id: [],
        list_sub_agents=lambda _agent_config_id: [],
    )

    result = await panel_router.list_agents(
        user_id="user-1",
        request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(user_repo=fake_repo, agent_config_repo=fake_agent_config_repo))),
    )

    assert seen == ["user-1"]
    assert result["items"][0]["id"] == "agent-1"
    assert result["items"][0]["name"] == "Toad"
    assert result["items"][0]["source"] == {"marketplace_item_id": "item-1", "installed_version": "1.0.0"}
    assert "config" not in result["items"][0]


@pytest.mark.asyncio
async def test_panel_agent_detail_keeps_full_config_for_owner_scope(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    agent = UserRow(
        id="agent-1",
        type=UserType.AGENT,
        display_name="Toad",
        owner_user_id="user-1",
        agent_config_id="cfg-1",
        created_at=1.0,
    )
    fake_repo = SimpleNamespace(
        get_by_id=lambda agent_id: agent if agent_id == "agent-1" else None,
    )
    fake_agent_config_repo = SimpleNamespace(
        get_config=lambda agent_config_id: {
            "id": agent_config_id,
            "name": "Toad",
            "description": "",
            "tools": ["*"],
            "system_prompt": "hello",
            "status": "draft",
            "version": "0.1.0",
            "runtime": {},
            "mcp": {},
            "created_at": 1,
            "updated_at": 2,
        },
        list_rules=lambda _agent_config_id: [],
        list_skills=lambda _agent_config_id: [],
        list_sub_agents=lambda _agent_config_id: [],
    )

    result = await panel_router.get_agent(
        "agent-1",
        user_id="user-1",
        request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(user_repo=fake_repo, agent_config_repo=fake_agent_config_repo))),
    )

    assert result["id"] == "agent-1"
    assert result["config"]["prompt"] == "hello"
    assert {agent["name"] for agent in result["config"]["subAgents"]} >= {"bash", "explore", "general", "plan"}


def test_owned_agent_helper_returns_agent_for_owner():
    result = panel_router._require_owned_agent_user(
        "agent-1",
        "user-1",
        SimpleNamespace(
            get_by_id=lambda user_id: _agent_user(user_id=user_id) if user_id == "agent-1" else None,
        ),
    )

    assert result.id == "agent-1"


def test_owned_agent_helper_raises_404_for_missing_agent():
    with pytest.raises(HTTPException) as excinfo:
        panel_router._require_owned_agent_user("missing", "user-1", SimpleNamespace(get_by_id=lambda _user_id: None))

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Agent not found"


def test_owned_agent_helper_raises_403_for_wrong_owner():
    with pytest.raises(HTTPException) as excinfo:
        panel_router._require_owned_agent_user(
            "agent-1",
            "user-1",
            SimpleNamespace(get_by_id=lambda _user_id: _agent_user(owner_user_id="user-2")),
        )

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "Forbidden"


@pytest.mark.asyncio
async def test_update_agent_route_returns_404_for_missing_agent(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(agent_user_service, "get_agent_user", lambda _agent_user_id: None)

    with pytest.raises(HTTPException) as excinfo:
        await panel_router.update_agent(
            "missing",
            UpdateAgentRequest(name="new-name"),
            request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(user_repo=SimpleNamespace(get_by_id=lambda _user_id: None)))),
            user_id="user-1",
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Agent not found"


@pytest.mark.asyncio
async def test_delete_agent_route_keeps_builtin_guard_before_owner_lookup(monkeypatch: pytest.MonkeyPatch):
    def explode(_agent_user_id: str):
        raise AssertionError("agent lookup should not run for builtin guard")

    monkeypatch.setattr(agent_user_service, "get_agent_user", explode)

    with pytest.raises(HTTPException) as excinfo:
        await panel_router.delete_agent(
            "__leon__",
            request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(user_repo=SimpleNamespace()))),
            user_id="user-1",
        )

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "Cannot delete builtin agent"


@pytest.mark.asyncio
async def test_delete_agent_route_rejects_agent_with_existing_threads(monkeypatch: pytest.MonkeyPatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("delete_agent should not run when agent still owns threads")

    monkeypatch.setattr(agent_user_service, "delete_agent_user", explode)

    with pytest.raises(HTTPException) as excinfo:
        await panel_router.delete_agent(
            "agent-1",
            request=SimpleNamespace(
                app=SimpleNamespace(
                    state=SimpleNamespace(
                        user_repo=SimpleNamespace(get_by_id=lambda user_id: _agent_user(user_id=user_id) if user_id == "agent-1" else None),
                        thread_repo=SimpleNamespace(list_by_agent_user=lambda agent_user_id: [{"id": f"{agent_user_id}-1"}]),
                    )
                )
            ),
            user_id="user-1",
        )

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == "Cannot delete agent with existing threads"


@pytest.mark.asyncio
async def test_delete_agent_route_passes_only_current_delete_dependencies(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, object] = {}

    def _fake_delete_agent_user(agent_id: str, **kwargs: object) -> bool:
        seen["agent_id"] = agent_id
        seen["delete_dependency_keys"] = sorted(kwargs)
        seen["contact_repo"] = kwargs.get("contact_repo")
        return True

    monkeypatch.setattr(agent_user_service, "delete_agent_user", _fake_delete_agent_user)

    contact_repo = object()
    result = await panel_router.delete_agent(
        "agent-1",
        request=SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    user_repo=SimpleNamespace(get_by_id=lambda user_id: _agent_user(user_id=user_id) if user_id == "agent-1" else None),
                    thread_repo=SimpleNamespace(list_by_agent_user=lambda _agent_user_id: []),
                    agent_config_repo=SimpleNamespace(),
                    contact_repo=contact_repo,
                )
            )
        ),
        user_id="user-1",
    )

    assert result == {"success": True}
    assert seen == {
        "agent_id": "agent-1",
        "delete_dependency_keys": ["agent_config_repo", "contact_repo", "user_repo"],
        "contact_repo": contact_repo,
    }


@pytest.mark.asyncio
async def test_publish_agent_route_keeps_builtin_guard_before_owner_lookup(monkeypatch: pytest.MonkeyPatch):
    def explode(_agent_user_id: str):
        raise AssertionError("agent lookup should not run for builtin guard")

    monkeypatch.setattr(agent_user_service, "get_agent_user", explode)

    with pytest.raises(HTTPException) as excinfo:
        await panel_router.publish_agent(
            "__leon__",
            PublishAgentRequest(),
            request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(user_repo=SimpleNamespace()))),
            user_id="user-1",
        )

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "Cannot publish builtin agent"


def test_profile_service_prefers_authenticated_member_over_config_defaults():
    user = UserRow(
        id="user-1",
        type=UserType.HUMAN,
        display_name="codex",
        email="codex@example.com",
        created_at=1.0,
    )

    profile = profile_service.get_profile(user=user)

    assert profile == {"name": "codex", "initials": "CO", "email": "codex@example.com"}


@pytest.mark.asyncio
async def test_profile_route_uses_authenticated_user_row_instead_of_requerying_repo():
    user = UserRow(
        id="user-1",
        type=UserType.HUMAN,
        display_name="codex",
        email="codex@example.com",
        created_at=1.0,
    )

    result = await panel_router.get_profile(
        user=user,
    )

    assert result == {"name": "codex", "initials": "CO", "email": "codex@example.com"}


def test_profile_service_updates_user_repo_shell_fields_only():
    seen: list[tuple[str, dict[str, object]]] = []

    class _UserRepo:
        def update(self, user_id: str, **fields):
            seen.append((user_id, fields))

        def get_by_id(self, user_id: str):
            if user_id != "user-1":
                return None
            return UserRow(
                id="user-1",
                type=UserType.HUMAN,
                display_name="renamed",
                email="renamed@example.com",
                created_at=1.0,
                updated_at=2.0,
            )

    profile = profile_service.update_profile(
        user_repo=_UserRepo(),
        user_id="user-1",
        name="renamed",
        email="renamed@example.com",
    )

    assert seen == [("user-1", {"display_name": "renamed", "email": "renamed@example.com"})]
    assert profile == {"name": "renamed", "initials": "RE", "email": "renamed@example.com"}


@pytest.mark.asyncio
async def test_update_profile_route_uses_user_repo_instead_of_config_file():
    seen: list[tuple[str, dict[str, object]]] = []

    class _UserRepo:
        def update(self, user_id: str, **fields):
            seen.append((user_id, fields))

        def get_by_id(self, user_id: str):
            if user_id != "user-1":
                return None
            return UserRow(
                id="user-1",
                type=UserType.HUMAN,
                display_name="renamed",
                email="renamed@example.com",
                created_at=1.0,
                updated_at=2.0,
            )

    result = await panel_router.update_profile(
        UpdateProfileRequest(name="renamed", initials="RN", email="renamed@example.com"),
        request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(user_repo=_UserRepo()))),
        user_id="user-1",
    )

    assert seen == [("user-1", {"display_name": "renamed", "email": "renamed@example.com"})]
    assert result == {"name": "renamed", "initials": "RE", "email": "renamed@example.com"}


def test_library_service_get_resource_used_by_scopes_to_owner(monkeypatch: pytest.MonkeyPatch):
    seen: list[tuple[str, object]] = []

    monkeypatch.setattr(
        agent_user_service,
        "list_agent_users",
        lambda owner_user_id=None, user_repo=None, agent_config_repo=None: (
            seen.append((owner_user_id, user_repo, agent_config_repo))
            or [
                {"id": "agent-1", "name": "Toad", "config": {"skills": [{"name": "skill-a"}]}},
                {"id": "agent-2", "name": "Dryad", "config": {"skills": [{"name": "skill-b"}]}},
            ]
        ),
    )

    result = library_service.get_resource_used_by("skill", "skill-a", "user-1", user_repo="repo-1", agent_config_repo="cfg-repo")

    assert result == ["Toad"]
    assert seen == [("user-1", "repo-1", "cfg-repo")]


def test_library_service_create_sandbox_template_uses_provider_name_identity(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        library_service.sandbox_service,
        "available_sandbox_types",
        lambda: [
            {"name": "daytona", "provider": "daytona", "available": True},
            {"name": "daytona_selfhost", "provider": "daytona", "available": True},
        ],
    )

    rows: dict[tuple[str, str], dict[str, object]] = {}

    class _RecipeRepo:
        def get(self, owner_user_id: str, recipe_id: str):
            return rows.get((owner_user_id, recipe_id))

        def upsert(self, **payload: object):
            rows[(str(payload["owner_user_id"]), str(payload["recipe_id"]))] = {"data": payload["data"], **payload}

    item = library_service.create_resource(
        "sandbox-template",
        "Selfhost Custom",
        "custom self-host sandbox",
        features={"lark_cli": True},
        provider_name="daytona_selfhost",
        owner_user_id="user-1",
        recipe_repo=_RecipeRepo(),
    )

    assert item["id"].startswith("daytona_selfhost:custom:")
    assert item["provider_name"] == "daytona_selfhost"
    assert item["provider_type"] == "daytona"
    assert rows[("user-1", item["id"])]["provider_type"] == "daytona"
    assert rows[("user-1", item["id"])]["data"]["provider_name"] == "daytona_selfhost"


def test_create_agent_user_fails_loudly_when_created_row_is_not_readable():
    created_rows: list[UserRow] = []
    saved_configs: list[tuple[str, dict[str, object]]] = []

    class _UserRepo:
        def create(self, row: UserRow) -> None:
            created_rows.append(row)

        def get_by_id(self, _user_id: str):
            return None

    class _AgentConfigRepo:
        def save_config(self, agent_config_id: str, data: dict[str, object]) -> None:
            saved_configs.append((agent_config_id, data))

    with pytest.raises(RuntimeError, match="Created agent user .* was not readable"):
        agent_user_service.create_agent_user(
            "Toad",
            "probe",
            owner_user_id="user-1",
            user_repo=_UserRepo(),
            agent_config_repo=_AgentConfigRepo(),
        )

    assert len(created_rows) == 1
    assert len(saved_configs) == 1


def test_create_agent_user_persists_owner_contact_edge():
    created_rows: dict[str, UserRow] = {}
    saved_configs: list[tuple[str, dict[str, object]]] = []
    contact_edges: list[object] = []

    class _UserRepo:
        def create(self, row: UserRow) -> None:
            created_rows[row.id] = row

        def get_by_id(self, user_id: str):
            return created_rows.get(user_id)

    class _AgentConfigRepo:
        def save_config(self, agent_config_id: str, data: dict[str, object]) -> None:
            saved_configs.append((agent_config_id, data))

        def get_config(self, agent_config_id: str):
            return saved_configs[-1][1] if saved_configs and saved_configs[-1][0] == agent_config_id else None

        def list_rules(self, _agent_config_id: str):
            return []

        def list_skills(self, _agent_config_id: str):
            return []

        def list_sub_agents(self, _agent_config_id: str):
            return []

    result = agent_user_service.create_agent_user(
        "Dryad",
        "probe",
        owner_user_id="user-1",
        user_repo=_UserRepo(),
        agent_config_repo=_AgentConfigRepo(),
        contact_repo=SimpleNamespace(upsert=lambda row: contact_edges.append(row)),
    )

    assert result["name"] == "Dryad"
    assert [(row.source_user_id, row.target_user_id, row.kind, row.state) for row in contact_edges] == [
        ("user-1", result["id"], "normal", "active"),
    ]


def test_agent_config_exposes_and_persists_compaction_trigger_tokens():
    agent = UserRow(
        id="agent-1",
        type=UserType.AGENT,
        display_name="Toad",
        owner_user_id="user-1",
        agent_config_id="cfg-1",
        created_at=1.0,
    )
    configs = {
        "cfg-1": {
            "agent_user_id": "agent-1",
            "name": "Toad",
            "description": "probe",
            "model": "leon:large",
            "tools": ["*"],
            "system_prompt": "",
            "status": "draft",
            "version": "0.1.0",
            "created_at": 1,
            "updated_at": 1,
            "runtime": {"tools:Bash": {"enabled": True, "desc": "shell"}},
            "compact": {"trigger_tokens": 80000},
            "mcp": {},
        }
    }

    class _AgentConfigRepo:
        def get_config(self, agent_config_id: str):
            return configs.get(agent_config_id)

        def save_config(self, agent_config_id: str, data: dict[str, object]) -> None:
            configs[agent_config_id] = data

        def list_rules(self, _agent_config_id: str):
            return []

        def list_skills(self, _agent_config_id: str):
            return []

        def list_sub_agents(self, _agent_config_id: str):
            return []

    user_repo = SimpleNamespace(get_by_id=lambda user_id: agent if user_id == "agent-1" else None)
    agent_config_repo = _AgentConfigRepo()

    before = agent_user_service.get_agent_user("agent-1", user_repo=user_repo, agent_config_repo=agent_config_repo)
    assert before["config"]["compact"] == {"trigger_tokens": 80000}

    after = agent_user_service.update_agent_user_config(
        "agent-1",
        {"compact": {"trigger_tokens": 100000}},
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )

    assert after["config"]["compact"] == {"trigger_tokens": 100000}
    assert configs["cfg-1"]["compact"] == {"trigger_tokens": 100000}
    assert configs["cfg-1"]["runtime"] == {"tools:Bash": {"enabled": True, "desc": "shell"}}


def test_get_agent_user_prefers_repo_skill_desc_over_library_fallback(monkeypatch: pytest.MonkeyPatch):
    agent = UserRow(
        id="agent-1",
        type=UserType.AGENT,
        display_name="Toad",
        owner_user_id="user-1",
        agent_config_id="cfg-1",
        created_at=1.0,
    )
    monkeypatch.setattr(library_service, "get_library_skill_desc", lambda _name: "library desc")

    class _AgentConfigRepo:
        def get_config(self, agent_config_id: str):
            assert agent_config_id == "cfg-1"
            return {
                "agent_user_id": "agent-1",
                "name": "Toad",
                "description": "probe",
                "model": "leon:large",
                "tools": ["*"],
                "system_prompt": "",
                "status": "draft",
                "version": "0.1.0",
                "created_at": 1,
                "updated_at": 1,
                "runtime": {},
                "mcp": {},
            }

        def list_rules(self, _agent_config_id: str):
            return []

        def list_skills(self, _agent_config_id: str):
            return [{"name": "Search", "content": "skill body", "meta_json": {"desc": "repo desc"}}]

        def list_sub_agents(self, _agent_config_id: str):
            return []

    result = agent_user_service.get_agent_user(
        "agent-1",
        user_repo=SimpleNamespace(get_by_id=lambda user_id: agent if user_id == "agent-1" else None),
        agent_config_repo=_AgentConfigRepo(),
    )

    assert result["config"]["skills"] == [{"name": "Search", "enabled": True, "desc": "repo desc"}]


def test_get_agent_user_keeps_runtime_skill_desc_override_ahead_of_repo_meta(monkeypatch: pytest.MonkeyPatch):
    agent = UserRow(
        id="agent-1",
        type=UserType.AGENT,
        display_name="Toad",
        owner_user_id="user-1",
        agent_config_id="cfg-1",
        created_at=1.0,
    )
    monkeypatch.setattr(library_service, "get_library_skill_desc", lambda _name: "library desc")

    class _AgentConfigRepo:
        def get_config(self, agent_config_id: str):
            assert agent_config_id == "cfg-1"
            return {
                "agent_user_id": "agent-1",
                "name": "Toad",
                "description": "probe",
                "model": "leon:large",
                "tools": ["*"],
                "system_prompt": "",
                "status": "draft",
                "version": "0.1.0",
                "created_at": 1,
                "updated_at": 1,
                "runtime": {"skills:Search": {"desc": "runtime desc"}},
                "mcp": {},
            }

        def list_rules(self, _agent_config_id: str):
            return []

        def list_skills(self, _agent_config_id: str):
            return [{"name": "Search", "content": "skill body", "meta_json": {"desc": "repo desc"}}]

        def list_sub_agents(self, _agent_config_id: str):
            return []

    result = agent_user_service.get_agent_user(
        "agent-1",
        user_repo=SimpleNamespace(get_by_id=lambda user_id: agent if user_id == "agent-1" else None),
        agent_config_repo=_AgentConfigRepo(),
    )

    assert result["config"]["skills"] == [{"name": "Search", "enabled": True, "desc": "runtime desc"}]


def test_get_agent_user_preserves_explicit_empty_repo_skill_desc(monkeypatch: pytest.MonkeyPatch):
    agent = UserRow(
        id="agent-1",
        type=UserType.AGENT,
        display_name="Toad",
        owner_user_id="user-1",
        agent_config_id="cfg-1",
        created_at=1.0,
    )
    monkeypatch.setattr(library_service, "get_library_skill_desc", lambda _name: "library desc")

    class _AgentConfigRepo:
        def get_config(self, agent_config_id: str):
            assert agent_config_id == "cfg-1"
            return {
                "agent_user_id": "agent-1",
                "name": "Toad",
                "description": "probe",
                "model": "leon:large",
                "tools": ["*"],
                "system_prompt": "",
                "status": "draft",
                "version": "0.1.0",
                "created_at": 1,
                "updated_at": 1,
                "runtime": {},
                "mcp": {},
            }

        def list_rules(self, _agent_config_id: str):
            return []

        def list_skills(self, _agent_config_id: str):
            return [{"name": "Search", "content": "skill body", "meta_json": {"desc": ""}}]

        def list_sub_agents(self, _agent_config_id: str):
            return []

    result = agent_user_service.get_agent_user(
        "agent-1",
        user_repo=SimpleNamespace(get_by_id=lambda user_id: agent if user_id == "agent-1" else None),
        agent_config_repo=_AgentConfigRepo(),
    )

    assert result["config"]["skills"] == [{"name": "Search", "enabled": True, "desc": ""}]


def test_install_from_snapshot_persists_skill_desc_from_snapshot_meta_into_repo_meta():
    saved_skill_rows: list[dict[str, object]] = []

    class _UserRepo:
        def create(self, _row: UserRow) -> None:
            return None

    class _AgentConfigRepo:
        def save_config(self, _agent_config_id: str, _data: dict[str, object]) -> None:
            return None

        def list_rules(self, _agent_config_id: str):
            return []

        def delete_rule(self, _row_id: str) -> None:
            return None

        def save_rule(self, _agent_config_id: str, _filename: str, _content: str) -> None:
            return None

        def list_skills(self, _agent_config_id: str):
            return []

        def delete_skill(self, _row_id: str) -> None:
            return None

        def save_skill(self, agent_config_id: str, name: str, content: str, meta: dict[str, object] | None = None) -> None:
            saved_skill_rows.append(
                {
                    "agent_config_id": agent_config_id,
                    "name": name,
                    "content": content,
                    "meta": meta,
                }
            )

        def list_sub_agents(self, _agent_config_id: str):
            return []

        def delete_sub_agent(self, _row_id: str) -> None:
            return None

        def save_sub_agent(self, *_args, **_kwargs) -> None:
            return None

    agent_user_service.install_from_snapshot(
        snapshot={
            "agent_md": "---\nname: Repo Agent\n---\nhello\n",
            "skills": [
                {
                    "name": "Search",
                    "content": "skill body",
                    "meta": {"name": "Search", "desc": "repo desc"},
                }
            ],
        },
        name="Repo Agent",
        description="probe",
        marketplace_item_id="item-1",
        installed_version="1.0.0",
        owner_user_id="user-1",
        user_repo=_UserRepo(),
        agent_config_repo=_AgentConfigRepo(),
    )

    assert saved_skill_rows == [
        {
            "agent_config_id": saved_skill_rows[0]["agent_config_id"],
            "name": "Search",
            "content": "skill body",
            "meta": {"name": "Search", "desc": "repo desc"},
        }
    ]


def test_install_from_snapshot_copies_rules_skills_and_sub_agents_to_new_config():
    saved_configs: list[tuple[str, dict[str, object]]] = []
    saved_rules: list[tuple[str, str, str]] = []
    saved_skills: list[tuple[str, str, str, dict[str, object] | None]] = []
    saved_sub_agents: list[tuple[str, str, dict[str, object]]] = []

    class _UserRepo:
        def create(self, row: UserRow) -> None:
            assert row.agent_config_id is not None

    class _AgentConfigRepo:
        def save_config(self, agent_config_id: str, data: dict[str, object]) -> None:
            saved_configs.append((agent_config_id, data))

        def list_rules(self, _agent_config_id: str):
            return []

        def delete_rule(self, _row_id: str) -> None:
            return None

        def save_rule(self, agent_config_id: str, filename: str, content: str) -> None:
            saved_rules.append((agent_config_id, filename, content))

        def list_skills(self, _agent_config_id: str):
            return []

        def delete_skill(self, _row_id: str) -> None:
            return None

        def save_skill(self, agent_config_id: str, name: str, content: str, meta: dict[str, object] | None = None) -> None:
            saved_skills.append((agent_config_id, name, content, meta))

        def list_sub_agents(self, _agent_config_id: str):
            return []

        def delete_sub_agent(self, _row_id: str) -> None:
            return None

        def save_sub_agent(self, agent_config_id: str, name: str, **kwargs: object) -> None:
            saved_sub_agents.append((agent_config_id, name, kwargs))

    agent_user_service.install_from_snapshot(
        snapshot={
            "agent_md": "---\nname: Repo Agent\ndescription: Repo desc\nmodel: leon:large\ntools: [Read]\n---\nmain prompt\n",
            "rules": [{"name": "Rule/Unsafe", "content": "rule body"}],
            "skills": [{"name": "Search", "content": "skill body", "meta": {"desc": "skill desc"}}],
            "agents": [
                {
                    "name": "Scout",
                    "content": "---\nname: Scout\ndescription: scout desc\nmodel: leon:small\ntools: [Read, Write]\n---\nscout prompt\n",
                }
            ],
        },
        name="Repo Agent",
        description="probe",
        marketplace_item_id="item-1",
        installed_version="1.0.0",
        owner_user_id="user-1",
        user_repo=_UserRepo(),
        agent_config_repo=_AgentConfigRepo(),
    )

    assert len(saved_configs) == 1
    agent_config_id = saved_configs[0][0]
    assert saved_configs[0][1]["name"] == "Repo Agent"
    assert saved_configs[0][1]["system_prompt"] == "main prompt"
    assert saved_rules == [(agent_config_id, "Rule_Unsafe.md", "rule body")]
    assert saved_skills == [(agent_config_id, "Search", "skill body", {"desc": "skill desc"})]
    assert saved_sub_agents == [
        (
            agent_config_id,
            "Scout",
            {
                "description": "scout desc",
                "model": "leon:small",
                "tools": ["Read", "Write"],
                "system_prompt": "scout prompt",
            },
        )
    ]


def _agent_delete_runner(*, contact_error: str | None = None):
    agent = UserRow(
        id="agent-1",
        type=UserType.AGENT,
        display_name="Toad",
        owner_user_id="user-1",
        agent_config_id="cfg-1",
        created_at=1.0,
    )
    calls: list[str] = []

    class _UserRepo:
        def get_by_id(self, user_id: str):
            return agent if user_id == "agent-1" else None

        def delete(self, user_id: str) -> None:
            calls.append(f"user:{user_id}")

    class _AgentConfigRepo:
        def delete_config(self, agent_config_id: str) -> None:
            calls.append(f"config:{agent_config_id}")

    class _ContactRepo:
        def delete_for_user(self, user_id: str) -> None:
            calls.append(f"contacts:{user_id}")
            if contact_error:
                raise RuntimeError(contact_error)

    def _run():
        return agent_user_service.delete_agent_user(
            "agent-1",
            user_repo=_UserRepo(),
            agent_config_repo=_AgentConfigRepo(),
            contact_repo=_ContactRepo(),
        )

    return calls, _run


def test_delete_agent_user_clears_dependent_edges_before_agent_config():
    calls, run = _agent_delete_runner()

    assert run() is True
    assert calls == ["contacts:agent-1", "config:cfg-1", "user:agent-1"]


def test_delete_agent_user_uses_current_delete_dependency_order_without_legacy_cleanup():
    agent = _agent_user(user_id="agent-1")
    calls: list[str] = []

    class _UserRepo:
        def get_by_id(self, user_id: str):
            return agent if user_id == "agent-1" else None

        def delete(self, user_id: str) -> None:
            calls.append(f"user:{user_id}")

    class _AgentConfigRepo:
        def delete_config(self, agent_config_id: str) -> None:
            calls.append(f"config:{agent_config_id}")

    class _ContactRepo:
        def delete_for_user(self, user_id: str) -> None:
            calls.append(f"contacts:{user_id}")

    assert agent_user_service.delete_agent_user(
        "agent-1",
        user_repo=_UserRepo(),
        agent_config_repo=_AgentConfigRepo(),
        contact_repo=_ContactRepo(),
    )
    assert calls == ["contacts:agent-1", "config:cfg-1", "user:agent-1"]


def test_delete_agent_user_does_not_remove_config_when_contact_cleanup_fails():
    calls, run = _agent_delete_runner(contact_error="contact cleanup failed")

    with pytest.raises(RuntimeError, match="contact cleanup failed"):
        run()

    assert calls == ["contacts:agent-1"]


@pytest.mark.asyncio
async def test_panel_library_used_by_route_uses_user_scope(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        library_service,
        "get_resource_used_by",
        lambda resource_type, resource_name, owner_user_id, user_repo=None, agent_config_repo=None: (
            seen.update(
                {
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "owner_user_id": owner_user_id,
                    "user_repo": user_repo,
                    "agent_config_repo": agent_config_repo,
                }
            )
            or ["Toad"]
        ),
    )

    fake_user_repo = SimpleNamespace()
    fake_agent_config_repo = SimpleNamespace()
    result = await panel_router.get_used_by(
        "skill",
        "skill-a",
        request=SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(user_repo=fake_user_repo, agent_config_repo=fake_agent_config_repo))
        ),
        user_id="user-1",
    )

    assert result == {"count": 1, "users": ["Toad"]}
    assert seen == {
        "resource_type": "skill",
        "resource_name": "skill-a",
        "owner_user_id": "user-1",
        "user_repo": fake_user_repo,
        "agent_config_repo": fake_agent_config_repo,
    }


def test_builtin_agent_surface_exposes_chat_tools():
    agent = agent_user_service._leon_builtin()
    tools = {item["name"]: item for item in agent["config"]["tools"]}

    for tool_name in ("list_chats", "read_messages", "send_message", "search_messages"):
        assert tool_name in tools
        assert tools[tool_name]["enabled"] is True
        assert tools[tool_name]["group"] == "chat"

    for removed_name in ("chats", "read_message", "search_message", "directory", "wechat_send", "wechat_contacts"):
        assert removed_name not in tools


def _agent_user(*, user_id: str = "agent-1", owner_user_id: str = "user-1") -> UserRow:
    return UserRow(
        id=user_id,
        type=UserType.AGENT,
        display_name="Toad",
        owner_user_id=owner_user_id,
        agent_config_id="cfg-1",
        created_at=1.0,
    )
