from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.library import service as library_service
from backend.threads import agent_user_service
from backend.web.models.panel import PublishAgentRequest, UpdateAgentRequest
from backend.web.routers import panel as panel_router
from config.agent_config_types import AgentConfig, AgentSkill, AgentSubAgent, McpServerConfig, Skill, SkillPackage
from storage.contracts import UserRow, UserType


def _runtime_storage_state(
    agent_config_repo: object,
    *,
    skill_repo: object | None = None,
    recipe_repo: object | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        storage_container=SimpleNamespace(
            agent_config_repo=lambda: agent_config_repo,
            skill_repo=lambda: skill_repo,
        ),
        recipe_repo=recipe_repo,
    )


def _agent_config(**updates: object) -> AgentConfig:
    data = {
        "id": "cfg-1",
        "owner_user_id": "user-1",
        "agent_user_id": "agent-1",
        "name": "Toad",
        "description": "",
        "tools": ["*"],
        "system_prompt": "hello",
        "status": "draft",
        "version": "0.1.0",
        "runtime_settings": {},
        "compact": {},
        "mcp_servers": [],
        "meta": {},
    }
    data.update(updates)
    return AgentConfig(**data)


class _MemorySkillRepo:
    def __init__(self) -> None:
        self.skills: dict[tuple[str, str], Skill] = {}
        self.packages: dict[tuple[str, str], SkillPackage] = {}

    def list_for_owner(self, owner_user_id: str) -> list[Skill]:
        return [skill for (owner, _skill_id), skill in self.skills.items() if owner == owner_user_id]

    def get_by_id(self, owner_user_id: str, skill_id: str) -> Skill | None:
        return self.skills.get((owner_user_id, skill_id))

    def upsert(self, skill: Skill) -> Skill:
        self.skills[(skill.owner_user_id, skill.id)] = skill
        return skill

    def create_package(self, package: SkillPackage) -> SkillPackage:
        self.packages[(package.owner_user_id, package.id)] = package
        return package

    def get_package(self, owner_user_id: str, package_id: str) -> SkillPackage | None:
        return self.packages.get((owner_user_id, package_id))

    def select_package(self, owner_user_id: str, skill_id: str, package_id: str) -> None:
        skill = self.skills[(owner_user_id, skill_id)]
        self.skills[(owner_user_id, skill_id)] = skill.model_copy(update={"package_id": package_id})

    def delete(self, owner_user_id: str, skill_id: str) -> None:
        self.skills.pop((owner_user_id, skill_id), None)


def _put_skill(
    skill_repo: _MemorySkillRepo,
    *,
    owner_user_id: str,
    skill_id: str,
    name: str,
    description: str,
    content: str,
    files: dict[str, str] | None = None,
    version: str = "1.0.0",
) -> Skill:
    timestamp = datetime(2026, 4, 24, tzinfo=UTC)
    skill = skill_repo.upsert(
        Skill(
            id=skill_id,
            owner_user_id=owner_user_id,
            name=name,
            description=description,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    package = skill_repo.create_package(
        SkillPackage(
            id=f"{skill_id}-package",
            owner_user_id=owner_user_id,
            skill_id=skill_id,
            version=version,
            hash=f"sha256:{skill_id}",
            manifest={"files": [{"path": path} for path in sorted(files or {})]},
            skill_md=content,
            files=files or {},
            created_at=timestamp,
        )
    )
    skill_repo.select_package(owner_user_id, skill_id, package.id)
    return skill_repo.get_by_id(owner_user_id, skill_id) or skill


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
        get_agent_config=lambda agent_config_id: _agent_config(
            id=agent_config_id,
            meta={"source": {"marketplace_item_id": "item-1", "source_version": "1.0.0"}},
        ),
    )

    result = await panel_router.list_agents(
        user_id="user-1",
        request=SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(user_repo=fake_repo, runtime_storage_state=_runtime_storage_state(fake_agent_config_repo))
            )
        ),
    )

    assert seen == ["user-1"]
    assert result["items"][0]["id"] == "agent-1"
    assert result["items"][0]["name"] == "Toad"
    assert result["items"][0]["source"] == {"marketplace_item_id": "item-1", "source_version": "1.0.0"}
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
        get_agent_config=lambda agent_config_id: _agent_config(id=agent_config_id),
    )

    result = await panel_router.get_agent(
        "agent-1",
        user_id="user-1",
        request=SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(user_repo=fake_repo, runtime_storage_state=_runtime_storage_state(fake_agent_config_repo))
            )
        ),
    )

    assert result["id"] == "agent-1"
    assert result["config"]["prompt"] == "hello"
    assert {agent["name"] for agent in result["config"]["subAgents"]} >= {"bash", "explore", "general", "plan"}


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
            thread_repo=SimpleNamespace(),
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
                        chat_runtime_state=SimpleNamespace(contact_repo=SimpleNamespace()),
                    )
                )
            ),
            user_id="user-1",
            thread_repo=SimpleNamespace(list_by_agent_user=lambda agent_user_id: [{"id": f"{agent_user_id}-1"}]),
        )

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == "Cannot delete agent with existing threads"


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


def test_create_agent_user_fails_loudly_when_created_row_is_not_readable():
    created_rows: list[UserRow] = []
    saved_configs: list[AgentConfig] = []

    class _UserRepo:
        def create(self, row: UserRow) -> None:
            created_rows.append(row)

        def get_by_id(self, _user_id: str):
            return None

    class _AgentConfigRepo:
        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

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
    saved_configs: list[AgentConfig] = []
    contact_edges: list[object] = []

    class _UserRepo:
        def create(self, row: UserRow) -> None:
            created_rows[row.id] = row

        def get_by_id(self, user_id: str):
            return created_rows.get(user_id)

    class _AgentConfigRepo:
        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

        def get_agent_config(self, agent_config_id: str):
            return saved_configs[-1] if saved_configs and saved_configs[-1].id == agent_config_id else None

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


def test_repo_backed_tools_star_keeps_panel_and_runtime_tool_state_aligned() -> None:
    from core.runtime.agent import LeonAgent

    config = _agent_config(tools=["*"])

    panel_lsp = next(item for item in agent_user_service._tools_from_repo(config) if item["name"] == "LSP")

    agent = LeonAgent.__new__(LeonAgent)
    agent._resolved_agent_config = config

    assert panel_lsp["enabled"] is True
    assert "LSP" not in agent._get_agent_blocked_tools()


def test_repo_backed_empty_tool_list_means_no_tools_enabled() -> None:
    config = _agent_config(tools=[])

    assert all(item["enabled"] is False for item in agent_user_service._tools_from_repo(config))


def test_repo_backed_named_tool_list_enables_only_named_tools() -> None:
    config = _agent_config(tools=["Read"])
    tools = {item["name"]: item["enabled"] for item in agent_user_service._tools_from_repo(config)}

    assert tools["Read"] is True
    assert tools["Bash"] is False


def test_repo_backed_empty_sub_agent_tool_list_means_no_tools_enabled() -> None:
    config = _agent_config(sub_agents=[AgentSubAgent(name="Worker", tools=[])])

    worker = next(item for item in agent_user_service._sub_agents_from_repo(config) if item["name"] == "Worker")

    assert all(item["enabled"] is False for item in worker["tools"])


def test_repo_backed_named_sub_agent_tool_list_enables_only_named_tools() -> None:
    config = _agent_config(sub_agents=[AgentSubAgent(name="Worker", tools=["Read"])])

    worker = next(item for item in agent_user_service._sub_agents_from_repo(config) if item["name"] == "Worker")
    tools = {item["name"]: item["enabled"] for item in worker["tools"]}

    assert tools["Read"] is True
    assert tools["Bash"] is False


def test_agent_config_patch_saves_library_skill_package_choice() -> None:
    saved_configs: list[AgentConfig] = []
    skill_repo = _MemorySkillRepo()
    library_skill = _put_skill(
        skill_repo,
        owner_user_id="user-1",
        skill_id="loadable-skill",
        name="Loadable Skill",
        description="loadable",
        content="---\nname: Loadable Skill\n---\nUse it.",
    )

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(skills=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    result = agent_user_service.update_agent_user_config(
        "agent-1",
        {"skills": [{"name": "Loadable Skill", "desc": "loadable", "enabled": True}]},
        user_repo=SimpleNamespace(
            get_by_id=lambda _agent_id: UserRow(
                id="agent-1",
                type=UserType.AGENT,
                display_name="Toad",
                owner_user_id="user-1",
                agent_config_id="cfg-1",
                created_at=1,
            )
        ),
        agent_config_repo=_AgentConfigRepo(),
        skill_repo=skill_repo,
    )

    assert result is not None
    assert saved_configs[-1].skills == [
        AgentSkill(
            id=None,
            skill_id="loadable-skill",
            package_id=library_skill.package_id,
            name="Loadable Skill",
            description="loadable",
            version="1.0.0",
        )
    ]


def test_agent_config_patch_rejects_inline_skill_content() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(skills=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="Skill patch item must not include content or files"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"skills": [{"name": "Inline Skill", "content": "---\nname: Inline Skill\n---\nUse it.", "enabled": True}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="user-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
            skill_repo=_MemorySkillRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_skill_disabled_flag() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(skills=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="Skill patch item must use enabled, not disabled"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"skills": [{"name": "Loadable Skill", "disabled": False}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="user-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
            skill_repo=_MemorySkillRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_skill_enabled_string() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(skills=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="Skill patch item enabled must be a boolean"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"skills": [{"name": "Loadable Skill", "enabled": "false"}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="user-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
            skill_repo=_MemorySkillRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_library_id_in_skill_name_field() -> None:
    saved_configs: list[AgentConfig] = []
    skill_repo = _MemorySkillRepo()
    _put_skill(
        skill_repo,
        owner_user_id="user-1",
        skill_id="loadable-skill",
        name="Loadable Skill",
        description="loadable",
        content="---\nname: Loadable Skill\n---\nUse it.",
    )

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(skills=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="Library skill not found: loadable-skill"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"skills": [{"name": "loadable-skill", "desc": "loadable", "enabled": True}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="user-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
            skill_repo=skill_repo,
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_skill_item_without_name() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(skills=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="Skill patch item must include name"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"skills": [{"enabled": True}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="user-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
            skill_repo=_MemorySkillRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_duplicate_skill_names() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(skills=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="Duplicate Skill name in patch: Loadable Skill"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {
                "skills": [
                    {"name": "Loadable Skill"},
                    {"name": "Loadable Skill"},
                ]
            },
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="user-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
            skill_repo=_MemorySkillRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_skill_after_library_delete() -> None:
    saved_configs: list[AgentConfig] = []
    selected = AgentSkill(
        id="agent-skill-1",
        skill_id="loadable-skill",
        package_id="loadable-package",
        name="Loadable Skill",
        description="loadable",
        source={"source_version": "1.0.0"},
    )

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(skills=[selected])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="Library skill not found: Loadable Skill"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"skills": [{"name": "Loadable Skill", "desc": "loadable", "enabled": False}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="user-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
            skill_repo=_MemorySkillRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_missing_explicit_library_skill_id() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(skills=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="Library skill not found: missing-skill"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {
                "skills": [
                    {
                        "skill_id": "missing-skill",
                        "name": "Inline Skill",
                    }
                ]
            },
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="user-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
            skill_repo=_MemorySkillRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_explicit_library_id_uses_library_package_choice() -> None:
    saved_configs: list[AgentConfig] = []
    skill_repo = _MemorySkillRepo()
    library_skill = _put_skill(
        skill_repo,
        owner_user_id="user-1",
        skill_id="loadable-skill",
        name="Loadable Skill",
        description="loadable",
        content="---\nname: Loadable Skill\n---\nLibrary content.",
    )

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(skills=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    result = agent_user_service.update_agent_user_config(
        "agent-1",
        {
            "skills": [
                {
                    "skill_id": "loadable-skill",
                    "name": "Loadable Skill",
                    "enabled": True,
                }
            ]
        },
        user_repo=SimpleNamespace(
            get_by_id=lambda _agent_id: UserRow(
                id="agent-1",
                type=UserType.AGENT,
                display_name="Toad",
                owner_user_id="user-1",
                agent_config_id="cfg-1",
                created_at=1,
            )
        ),
        agent_config_repo=_AgentConfigRepo(),
        skill_repo=skill_repo,
    )

    assert result is not None
    assert saved_configs[-1].skills[0].skill_id == "loadable-skill"
    assert saved_configs[-1].skills[0].package_id == library_skill.package_id
    assert "content" not in saved_configs[-1].skills[0].model_dump()


def test_panel_library_skill_routes_use_skill_repo_without_recipe_repo() -> None:
    app = FastAPI()
    app.include_router(panel_router.router)
    app.dependency_overrides[panel_router.get_current_user_id] = lambda: "owner-1"
    skill_repo = _MemorySkillRepo()
    app.state.runtime_storage_state = _runtime_storage_state(SimpleNamespace(), skill_repo=skill_repo)

    with TestClient(app) as client:
        created = client.post("/api/panel/library/skill", json={"name": "Loadable Skill", "desc": "Use this skill"})
        assert created.status_code == 200
        assert created.json()["id"] == "loadable-skill"

        listed = client.get("/api/panel/library/skill")
        assert listed.status_code == 200
        assert listed.json()["items"][0]["name"] == "Loadable Skill"

        content = client.get("/api/panel/library/skill/loadable-skill/content")
        assert content.status_code == 200
        assert content.json()["content"] == "---\nname: Loadable Skill\ndescription: Use this skill\n---\n\nUse this skill\n"


def test_library_skill_content_update_rejects_frontmatter_name_drift() -> None:
    skill_repo = _MemorySkillRepo()
    created = library_service.create_resource(
        "skill",
        "Loadable Skill",
        "Use this skill",
        owner_user_id="owner-1",
        skill_repo=skill_repo,
    )

    with pytest.raises(ValueError, match="frontmatter name must match Skill name"):
        library_service.update_resource_content(
            "skill",
            created["id"],
            "---\nname: Runtime Skill\n---\n\nUse it.",
            owner_user_id="owner-1",
            skill_repo=skill_repo,
        )

    stored = skill_repo.get_by_id("owner-1", created["id"])
    assert stored is not None and stored.package_id is not None
    assert (
        skill_repo.get_package("owner-1", stored.package_id).skill_md
        == "---\nname: Loadable Skill\ndescription: Use this skill\n---\n\nUse this skill\n"
    )


def test_library_skill_name_is_immutable_after_creation() -> None:
    skill_repo = _MemorySkillRepo()
    created = library_service.create_resource(
        "skill",
        "Loadable Skill",
        "Use this skill",
        owner_user_id="owner-1",
        skill_repo=skill_repo,
    )

    with pytest.raises(ValueError, match="Skill name is immutable"):
        library_service.update_resource(
            "skill",
            created["id"],
            owner_user_id="owner-1",
            skill_repo=skill_repo,
            name="Renamed Skill",
        )

    assert skill_repo.get_by_id("owner-1", created["id"]).name == "Loadable Skill"


def test_library_skill_create_rejects_slug_collision_with_different_name() -> None:
    skill_repo = _MemorySkillRepo()
    created = library_service.create_resource(
        "skill",
        "Loadable Skill",
        "Use this skill",
        owner_user_id="owner-1",
        skill_repo=skill_repo,
    )

    with pytest.raises(ValueError, match="Skill id already exists with a different Skill name"):
        library_service.create_resource(
            "skill",
            "Loadable-Skill",
            "Different name, same slug",
            owner_user_id="owner-1",
            skill_repo=skill_repo,
        )

    stored = skill_repo.get_by_id("owner-1", created["id"])
    assert stored is not None
    assert stored.name == "Loadable Skill"
    assert stored.description == "Use this skill"


def test_library_rejects_agent_resource_type() -> None:
    with pytest.raises(ValueError, match="Unknown resource type: agent"):
        library_service.list_library("agent")


def test_library_rejects_mcp_resource_type() -> None:
    with pytest.raises(ValueError, match="Unknown resource type: mcp"):
        library_service.list_library("mcp")


def test_agent_config_patch_persists_explicit_mcp_config() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(system_prompt="")

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    result = agent_user_service.update_agent_user_config(
        "agent-1",
        {
            "mcpServers": [
                {
                    "name": "demo-mcp",
                    "transport": "stdio",
                    "command": "uv",
                    "args": ["run", "python", "/tmp/demo_mcp.py"],
                    "env": {"DEMO": "1"},
                    "allowed_tools": ["read"],
                    "instructions": "Use demo resources.",
                    "enabled": True,
                }
            ]
        },
        user_repo=SimpleNamespace(
            get_by_id=lambda _agent_id: UserRow(
                id="agent-1",
                type=UserType.AGENT,
                display_name="Toad",
                owner_user_id="owner-1",
                agent_config_id="cfg-1",
                created_at=1,
            )
        ),
        agent_config_repo=_AgentConfigRepo(),
    )

    assert result is not None
    assert saved_configs[-1].mcp_servers == [
        McpServerConfig(
            name="demo-mcp",
            transport="stdio",
            command="uv",
            args=["run", "python", "/tmp/demo_mcp.py"],
            env={"DEMO": "1"},
            allowed_tools=["read"],
            instructions="Use demo resources.",
        )
    ]


def test_agent_config_patch_rejects_mcp_item_without_name() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(mcp_servers=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="MCP server patch item must include name"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"mcpServers": [{"enabled": True}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="user-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
            skill_repo=_MemorySkillRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_persists_mcp_enabled_false() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(system_prompt="", mcp_servers=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    result = agent_user_service.update_agent_user_config(
        "agent-1",
        {"mcpServers": [{"name": "demo-mcp", "transport": "stdio", "command": "uv", "enabled": False}]},
        user_repo=SimpleNamespace(
            get_by_id=lambda _agent_id: UserRow(
                id="agent-1",
                type=UserType.AGENT,
                display_name="Toad",
                owner_user_id="owner-1",
                agent_config_id="cfg-1",
                created_at=1,
            )
        ),
        agent_config_repo=_AgentConfigRepo(),
    )

    assert result is not None
    assert saved_configs[-1].mcp_servers == [McpServerConfig(name="demo-mcp", transport="stdio", command="uv", enabled=False)]


def test_agent_config_patch_rejects_mcp_disabled_flag() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(mcp_servers=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="MCP server patch item must use enabled, not disabled"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"mcpServers": [{"name": "demo-mcp", "transport": "stdio", "command": "uv", "disabled": False}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="owner-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_mcp_enabled_string() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(mcp_servers=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="MCP server patch item enabled must be a boolean"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"mcpServers": [{"name": "demo-mcp", "transport": "stdio", "command": "uv", "enabled": "false"}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="owner-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_mcp_args_object() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(mcp_servers=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="MCP server patch item args must be a JSON array"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"mcpServers": [{"name": "demo-mcp", "transport": "stdio", "command": "uv", "args": {"root": "."}}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="owner-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_mcp_env_array() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(mcp_servers=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="MCP server patch item env must be a JSON object"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"mcpServers": [{"name": "demo-mcp", "transport": "stdio", "command": "uv", "env": ["A=B"]}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="owner-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_duplicate_mcp_server_names() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(mcp_servers=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="Duplicate MCP server name in patch: demo-mcp"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {
                "mcpServers": [
                    {"name": "demo-mcp", "command": "one"},
                    {"name": "demo-mcp", "command": "two"},
                ]
            },
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="user-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
            skill_repo=_MemorySkillRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_rule_item_without_name() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config()

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="Rule patch item must include name"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"rules": [{"content": "body"}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="user-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
            skill_repo=_MemorySkillRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_duplicate_rule_names() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config()

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="Duplicate Rule name in patch: coding"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"rules": [{"name": "coding", "content": "one"}, {"name": "coding", "content": "two"}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="user-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
            skill_repo=_MemorySkillRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_sub_agent_item_without_name() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config()

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="SubAgent patch item must include name"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"subAgents": [{"description": "scout"}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="user-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
            skill_repo=_MemorySkillRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_duplicate_sub_agent_names() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config()

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="Duplicate SubAgent name in patch: Scout"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"subAgents": [{"name": "Scout"}, {"name": "Scout"}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="user-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
            skill_repo=_MemorySkillRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_sub_agent_tool_enabled_string() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config()

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="SubAgent tool patch item enabled must be a boolean"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"subAgents": [{"name": "Scout", "tools": [{"name": "Read", "enabled": "false"}]}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="user-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
            skill_repo=_MemorySkillRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_sub_agent_tools_object() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config()

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="SubAgent patch item tools must be a JSON array"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"subAgents": [{"name": "Scout", "tools": {"Read": True}}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="user-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
            skill_repo=_MemorySkillRepo(),
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_mcp_without_runtime_target() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(mcp_servers=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="MCP server config must include command or url: demo-mcp"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"mcpServers": [{"name": "demo-mcp", "enabled": True}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="user-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
            skill_repo=_MemorySkillRepo(),
        )

    assert saved_configs == []


def test_agent_config_exposes_mcp_config_fields_for_lossless_toggle() -> None:
    agent = UserRow(
        id="agent-1",
        type=UserType.AGENT,
        display_name="Toad",
        owner_user_id="user-1",
        agent_config_id="cfg-1",
        created_at=1.0,
    )

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(
                description="probe",
                model="leon:large",
                system_prompt="",
                mcp_servers=[
                    McpServerConfig(
                        name="demo-mcp",
                        transport="streamable_http",
                        url="http://127.0.0.1:8765/mcp",
                        env={"DEMO": "1"},
                        allowed_tools=["read"],
                        instructions="Use demo resources.",
                    )
                ],
            )

    result = agent_user_service.get_agent_user(
        "agent-1",
        user_repo=SimpleNamespace(get_by_id=lambda user_id: agent if user_id == "agent-1" else None),
        agent_config_repo=_AgentConfigRepo(),
    )

    assert result is not None
    assert result["config"]["mcpServers"] == [
        {
            "name": "demo-mcp",
            "transport": "streamable_http",
            "url": "http://127.0.0.1:8765/mcp",
            "env": {"DEMO": "1"},
            "allowed_tools": ["read"],
            "instructions": "Use demo resources.",
            "enabled": True,
        }
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
        "cfg-1": _agent_config(
            description="probe",
            model="leon:large",
            system_prompt="",
            runtime_settings={"tools:Bash": {"enabled": True, "desc": "shell"}},
            compact={"trigger_tokens": 80000},
        )
    }

    class _AgentConfigRepo:
        def get_agent_config(self, agent_config_id: str):
            return configs.get(agent_config_id)

        def save_agent_config(self, config: AgentConfig) -> None:
            configs[config.id] = config

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
    assert configs["cfg-1"].compact == {"trigger_tokens": 100000}
    assert configs["cfg-1"].runtime_settings == {"tools:Bash": {"enabled": True, "desc": "shell"}}


def test_agent_config_patch_rejects_tool_enabled_string() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(runtime_settings={})

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="Tool patch item enabled must be a boolean"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"tools": [{"name": "Bash", "enabled": "false"}]},
            user_repo=SimpleNamespace(
                get_by_id=lambda _agent_id: UserRow(
                    id="agent-1",
                    type=UserType.AGENT,
                    display_name="Toad",
                    owner_user_id="user-1",
                    agent_config_id="cfg-1",
                    created_at=1,
                )
            ),
            agent_config_repo=_AgentConfigRepo(),
        )

    assert saved_configs == []


def test_get_agent_user_uses_repo_skill_desc():
    agent = UserRow(
        id="agent-1",
        type=UserType.AGENT,
        display_name="Toad",
        owner_user_id="user-1",
        agent_config_id="cfg-1",
        created_at=1.0,
    )

    class _AgentConfigRepo:
        def get_agent_config(self, agent_config_id: str):
            assert agent_config_id == "cfg-1"
            return _agent_config(
                description="probe",
                model="leon:large",
                system_prompt="",
                skills=[AgentSkill(skill_id="search", package_id="search-package", name="Search", description="repo desc")],
            )

    result = agent_user_service.get_agent_user(
        "agent-1",
        user_repo=SimpleNamespace(get_by_id=lambda user_id: agent if user_id == "agent-1" else None),
        agent_config_repo=_AgentConfigRepo(),
    )

    assert result["config"]["skills"] == [{"name": "Search", "enabled": True, "desc": "repo desc"}]


def test_get_agent_user_ignores_runtime_skill_desc_override():
    agent = UserRow(
        id="agent-1",
        type=UserType.AGENT,
        display_name="Toad",
        owner_user_id="user-1",
        agent_config_id="cfg-1",
        created_at=1.0,
    )

    class _AgentConfigRepo:
        def get_agent_config(self, agent_config_id: str):
            assert agent_config_id == "cfg-1"
            return _agent_config(
                description="probe",
                model="leon:large",
                system_prompt="",
                runtime_settings={"skills:Search": {"desc": "runtime desc", "enabled": False}},
                skills=[AgentSkill(skill_id="search", package_id="search-package", name="Search", description="repo desc")],
            )

    result = agent_user_service.get_agent_user(
        "agent-1",
        user_repo=SimpleNamespace(get_by_id=lambda user_id: agent if user_id == "agent-1" else None),
        agent_config_repo=_AgentConfigRepo(),
    )

    assert result["config"]["skills"] == [{"name": "Search", "enabled": True, "desc": "repo desc"}]


@pytest.mark.asyncio
async def test_create_agent_route_fails_loud_when_contact_repo_missing():
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                user_repo=SimpleNamespace(),
                runtime_storage_state=_runtime_storage_state(SimpleNamespace()),
            )
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await panel_router.create_agent(
            panel_router.CreateAgentRequest(name="Toad", description="probe"),
            request=request,
            user_id="user-1",
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "chat bootstrap not attached: contact_repo"


@pytest.mark.asyncio
async def test_delete_agent_route_fails_loud_when_contact_repo_missing(monkeypatch: pytest.MonkeyPatch):
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                user_repo=SimpleNamespace(),
                runtime_storage_state=_runtime_storage_state(SimpleNamespace()),
                thread_repo=SimpleNamespace(list_by_agent_user=lambda _agent_id: []),
            )
        )
    )
    monkeypatch.setattr(panel_router, "_require_owned_agent_user", lambda *_args, **_kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        await panel_router.delete_agent(
            "agent-1",
            request=request,
            user_id="user-1",
            thread_repo=request.app.state.thread_repo,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "chat bootstrap not attached: contact_repo"


@pytest.mark.asyncio
async def test_delete_agent_route_fails_loud_when_thread_repo_missing(monkeypatch: pytest.MonkeyPatch):
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                user_repo=SimpleNamespace(),
                runtime_storage_state=_runtime_storage_state(SimpleNamespace()),
                chat_runtime_state=SimpleNamespace(contact_repo=SimpleNamespace()),
            )
        )
    )
    monkeypatch.setattr(panel_router, "_require_owned_agent_user", lambda *_args, **_kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        await panel_router.delete_agent(
            "agent-1",
            request=request,
            user_id="user-1",
            thread_repo=None,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Thread repo unavailable"


def test_panel_agents_http_surface_does_not_expose_query_app_param(monkeypatch: pytest.MonkeyPatch):
    app = FastAPI()
    app.include_router(panel_router.router)
    app.dependency_overrides[panel_router.get_current_user_id] = lambda: "user-1"
    app.state.user_repo = SimpleNamespace()
    app.state.runtime_storage_state = _runtime_storage_state(SimpleNamespace())
    app.state.thread_repo = SimpleNamespace(list_by_agent_user=lambda _agent_id: [])
    app.state.chat_runtime_state = SimpleNamespace(contact_repo=SimpleNamespace())

    monkeypatch.setattr(
        agent_user_service,
        "create_agent_user",
        lambda name, description="", **_kwargs: {"id": "agent-1", "name": name, "description": description},
    )
    monkeypatch.setattr(panel_router, "_require_owned_agent_user", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(agent_user_service, "delete_agent_user", lambda *_args, **_kwargs: True)

    with TestClient(app) as client:
        openapi = client.get("/openapi.json")
        create_params = openapi.json()["paths"]["/api/panel/agents"]["post"].get("parameters", [])
        delete_params = openapi.json()["paths"]["/api/panel/agents/{agent_id}"]["delete"].get("parameters", [])

        create = client.post(
            "/api/panel/agents",
            json={"name": "Toad", "description": "probe"},
            headers={"Authorization": "Bearer token"},
        )
        delete = client.delete("/api/panel/agents/agent-1", headers={"Authorization": "Bearer token"})

    assert create_params == []
    assert delete_params == [
        {
            "name": "agent_id",
            "in": "path",
            "required": True,
            "schema": {"type": "string", "title": "Agent Id"},
        }
    ]
    assert create.status_code == 200
    assert create.json() == {"id": "agent-1", "name": "Toad", "description": "probe"}
    assert delete.status_code == 200
    assert delete.json() == {"success": True}


def test_get_agent_user_preserves_explicit_empty_repo_skill_desc():
    agent = UserRow(
        id="agent-1",
        type=UserType.AGENT,
        display_name="Toad",
        owner_user_id="user-1",
        agent_config_id="cfg-1",
        created_at=1.0,
    )

    class _AgentConfigRepo:
        def get_agent_config(self, agent_config_id: str):
            assert agent_config_id == "cfg-1"
            return _agent_config(
                description="probe",
                model="leon:large",
                system_prompt="",
                skills=[AgentSkill(skill_id="search", package_id="search-package", name="Search", description="")],
            )

    result = agent_user_service.get_agent_user(
        "agent-1",
        user_repo=SimpleNamespace(get_by_id=lambda user_id: agent if user_id == "agent-1" else None),
        agent_config_repo=_AgentConfigRepo(),
    )

    assert result["config"]["skills"] == [{"name": "Search", "enabled": True, "desc": ""}]


def test_apply_snapshot_saves_one_agent_config_aggregate():
    from backend.hub.snapshot_apply import apply_snapshot

    created_users: list[UserRow] = []
    saved_configs: list[AgentConfig] = []
    skill_repo = _MemorySkillRepo()

    class _UserRepo:
        def create(self, row: UserRow) -> None:
            created_users.append(row)

    class _AgentConfigRepo:
        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    user_id = apply_snapshot(
        snapshot={
            "schema_version": "agent-snapshot/v1",
            "agent": {
                "id": "cfg-source",
                "name": "Repo Agent",
                "description": "Repo desc",
                "model": "leon:large",
                "tools": ["Read"],
                "system_prompt": "main prompt",
                "skills": [{"name": "Search", "content": "---\nname: Search\n---\nbody", "description": "skill desc"}],
                "rules": [{"name": "Rule_Unsafe", "content": "rule body"}],
                "sub_agents": [{"name": "Scout", "description": "scout desc", "tools": ["Read"], "system_prompt": "scout prompt"}],
            },
        },
        marketplace_item_id="item-1",
        source_version="1.0.0",
        owner_user_id="user-1",
        user_repo=_UserRepo(),
        agent_config_repo=_AgentConfigRepo(),
        skill_repo=skill_repo,
    )

    assert user_id == created_users[0].id
    assert saved_configs[0].name == "Repo Agent"
    assert saved_configs[0].skills[0].description == "skill desc"
    assert saved_configs[0].skills[0].skill_id == "search"
    assert saved_configs[0].skills[0].package_id
    assert skill_repo.get_by_id("user-1", "search") is not None
    package = skill_repo.get_package("user-1", saved_configs[0].skills[0].package_id or "")
    assert package is not None
    assert package.skill_md == "---\nname: Search\n---\nbody"
    assert saved_configs[0].rules[0].content == "rule body"
    assert saved_configs[0].sub_agents[0].name == "Scout"
    assert saved_configs[0].meta["source"]["source_version"] == "1.0.0"


def test_apply_snapshot_with_skills_requires_skill_repo():
    from backend.hub.snapshot_apply import apply_snapshot

    with pytest.raises(RuntimeError, match="skill_repo is required to apply snapshot Skills"):
        apply_snapshot(
            snapshot={
                "schema_version": "agent-snapshot/v1",
                "agent": {
                    "id": "cfg-source",
                    "name": "Repo Agent",
                    "skills": [{"name": "Search", "content": "---\nname: Search\n---\nbody"}],
                },
            },
            marketplace_item_id="item-1",
            source_version="1.0.0",
            owner_user_id="user-1",
            user_repo=SimpleNamespace(create=lambda _row: None),
            agent_config_repo=SimpleNamespace(save_agent_config=lambda _config: None),
        )


def test_apply_snapshot_rejects_duplicate_skill_names_before_library_write():
    from backend.hub.snapshot_apply import apply_snapshot

    skill_repo = _MemorySkillRepo()

    with pytest.raises(ValueError, match="Duplicate Skill name in snapshot: Search"):
        apply_snapshot(
            snapshot={
                "schema_version": "agent-snapshot/v1",
                "agent": {
                    "id": "cfg-source",
                    "name": "Repo Agent",
                    "skills": [
                        {"name": "Search", "content": "---\nname: Search\n---\none"},
                        {"name": "Search", "content": "---\nname: Search\n---\ntwo"},
                    ],
                },
            },
            marketplace_item_id="item-1",
            source_version="1.0.0",
            owner_user_id="user-1",
            user_repo=SimpleNamespace(create=lambda _row: None),
            agent_config_repo=SimpleNamespace(save_agent_config=lambda _config: None),
            skill_repo=skill_repo,
        )
    assert skill_repo.list_for_owner("user-1") == []


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
        def delete_agent_config(self, agent_config_id: str) -> None:
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
            app=SimpleNamespace(
                state=SimpleNamespace(
                    user_repo=fake_user_repo,
                    runtime_storage_state=_runtime_storage_state(fake_agent_config_repo),
                )
            )
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


def test_library_used_by_reads_agent_configs_without_display_projection(monkeypatch: pytest.MonkeyPatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("used-by must not depend on agent display projection")

    monkeypatch.setattr(agent_user_service, "list_agent_users", explode)
    agent = _agent_user(user_id="agent-1", owner_user_id="user-1")
    fake_user_repo = SimpleNamespace(list_by_owner_user_id=lambda owner_user_id: [agent] if owner_user_id == "user-1" else [])
    fake_agent_config_repo = SimpleNamespace(
        get_agent_config=lambda _config_id: _agent_config(
            skills=[
                AgentSkill(
                    skill_id="skill-1",
                    package_id="skill-1-package",
                    name="api-design-reviewer",
                    enabled=True,
                )
            ],
        )
    )

    assert library_service.get_resource_used_by(
        "skill",
        "api-design-reviewer",
        "user-1",
        user_repo=fake_user_repo,
        agent_config_repo=fake_agent_config_repo,
    ) == ["Toad"]


@pytest.mark.asyncio
async def test_delete_skill_route_rejects_skill_still_selected_by_agent(monkeypatch: pytest.MonkeyPatch):
    skill_repo = _MemorySkillRepo()
    _put_skill(
        skill_repo,
        owner_user_id="user-1",
        skill_id="skill-1",
        name="api-design-reviewer",
        description="API Design Reviewer",
        content="---\nname: api-design-reviewer\n---\nBody",
    )
    agent = _agent_user(user_id="agent-1", owner_user_id="user-1")
    fake_user_repo = SimpleNamespace(list_by_owner_user_id=lambda owner_user_id: [agent] if owner_user_id == "user-1" else [])
    fake_agent_config_repo = SimpleNamespace(
        get_agent_config=lambda _config_id: _agent_config(
            skills=[
                AgentSkill(
                    skill_id="skill-1",
                    package_id="skill-1-package",
                    name="api-design-reviewer",
                    enabled=True,
                )
            ],
        )
    )

    deleted: list[tuple[str, str]] = []
    monkeypatch.setattr(skill_repo, "delete", lambda owner_user_id, skill_id: deleted.append((owner_user_id, skill_id)))

    with pytest.raises(HTTPException) as excinfo:
        await panel_router.delete_resource(
            "skill",
            "skill-1",
            request=SimpleNamespace(
                app=SimpleNamespace(
                    state=SimpleNamespace(
                        user_repo=fake_user_repo,
                        runtime_storage_state=_runtime_storage_state(fake_agent_config_repo, skill_repo=skill_repo),
                    )
                )
            ),
            user_id="user-1",
        )

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == "Skill is still assigned to Agent: Toad"
    assert deleted == []


@pytest.mark.asyncio
async def test_delete_skill_route_allows_skill_after_agent_config_removal(monkeypatch: pytest.MonkeyPatch):
    skill_repo = _MemorySkillRepo()
    _put_skill(
        skill_repo,
        owner_user_id="user-1",
        skill_id="skill-1",
        name="api-design-reviewer",
        description="API Design Reviewer",
        content="---\nname: api-design-reviewer\n---\nBody",
    )
    agent = _agent_user(user_id="agent-1", owner_user_id="user-1")
    fake_user_repo = SimpleNamespace(list_by_owner_user_id=lambda owner_user_id: [agent] if owner_user_id == "user-1" else [])
    fake_agent_config_repo = SimpleNamespace(get_agent_config=lambda _config_id: _agent_config(skills=[]))

    result = await panel_router.delete_resource(
        "skill",
        "skill-1",
        request=SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    user_repo=fake_user_repo,
                    runtime_storage_state=_runtime_storage_state(fake_agent_config_repo, skill_repo=skill_repo),
                )
            )
        ),
        user_id="user-1",
    )

    assert result == {"success": True}
    assert skill_repo.get_by_id("user-1", "skill-1") is None


def test_builtin_agent_surface_exposes_chat_tools():
    agent = agent_user_service._leon_builtin()
    tools = {item["name"]: item for item in agent["config"]["tools"]}

    for tool_name in ("list_chats", "create_group_chat", "read_messages", "send_message", "search_messages"):
        assert tool_name in tools
        assert tools[tool_name]["enabled"] is True
        assert tools[tool_name]["group"] == "chat"


def _agent_user(*, user_id: str = "agent-1", owner_user_id: str = "user-1") -> UserRow:
    return UserRow(
        id=user_id,
        type=UserType.AGENT,
        display_name="Toad",
        owner_user_id=owner_user_id,
        agent_config_id="cfg-1",
        created_at=1.0,
    )
