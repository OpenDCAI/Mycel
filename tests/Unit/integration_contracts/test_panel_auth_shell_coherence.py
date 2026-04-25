from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

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


def _editable_skill_md(name: str = "Loadable Skill", description: str = "Use this skill", version: str = "1.0.0") -> str:
    return f"---\nname: {name}\ndescription: {description}\nversion: {version}\n---\n\n{description}\n"


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
async def test_panel_agent_detail_exposes_library_skill_id_for_round_trip() -> None:
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
        get_agent_config=lambda agent_config_id: _agent_config(
            id=agent_config_id,
            skills=[
                AgentSkill(
                    id="agent-skill-1",
                    skill_id="loadable-skill",
                    package_id="loadable-skill-package",
                    name="Loadable Skill",
                    description="loadable",
                    enabled=True,
                )
            ],
        ),
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

    assert result["config"]["skills"][0]["id"] == "loadable-skill"
    assert result["config"]["skills"][0]["name"] == "Loadable Skill"


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
        {"skills": [{"id": "loadable-skill", "enabled": True}]},
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
        )
    ]


def test_agent_config_patch_keeps_package_source_out_of_agent_skill_binding() -> None:
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
    skill_repo.upsert(library_skill.model_copy(update={"source": {"source_version": "library-stale"}}))

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(
                skills=[
                    AgentSkill(
                        id="agent-skill-1",
                        skill_id="loadable-skill",
                        package_id=library_skill.package_id,
                        name="Loadable Skill",
                    )
                ]
            )

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    agent_user_service.update_agent_user_config(
        "agent-1",
        {"skills": [{"id": "loadable-skill", "enabled": True}]},
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

    assert "source" not in saved_configs[-1].skills[0].model_dump()


def test_agent_config_patch_does_not_fill_skill_identity_from_patch_or_current_binding() -> None:
    import inspect

    source = inspect.getsource(agent_user_service._skills_from_patch)

    assert 'item.get("skill_id")' not in source
    assert "agent_skill_id" not in source
    assert "row_id" not in source
    assert 'item.get("version")' not in source
    assert "current_skill.version" not in source
    assert "library_skill.source" not in source
    assert 'item.get("source")' not in source
    assert "current_skill.source" not in source


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
            {"skills": [{"id": "loadable-skill", "content": "---\nname: Inline Skill\n---\nUse it.", "enabled": True}]},
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


@pytest.mark.parametrize("field", ["source", "version"])
def test_agent_config_patch_rejects_skill_content_identity_fields(field: str) -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(skills=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    patch_item = {"id": "loadable-skill", "enabled": True, field: {"source_version": "patch"} if field == "source" else "9.9.9"}

    with pytest.raises(RuntimeError, match="Skill patch item must not include source or version"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"skills": [patch_item]},
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
            {"skills": [{"id": "loadable-skill", "disabled": False}]},
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
            {"skills": [{"id": "loadable-skill", "enabled": "false"}]},
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


def test_agent_config_patch_rejects_skill_item_without_library_skill_id() -> None:
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

    with pytest.raises(RuntimeError, match="Skill patch item must include id"):
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
            skill_repo=skill_repo,
        )

    assert saved_configs == []


def test_agent_config_patch_rejects_skill_name_and_desc_fields() -> None:
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

    with pytest.raises(RuntimeError, match="Skill patch item must not include name or desc"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"skills": [{"id": "loadable-skill", "name": "Loadable Skill", "desc": "loadable", "enabled": True}]},
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


def test_agent_config_patch_rejects_non_object_skill_item() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(skills=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="Skill patch item must be an object"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"skills": ["loadable-skill"]},
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


def test_agent_config_patch_rejects_duplicate_skill_ids() -> None:
    saved_configs: list[AgentConfig] = []

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(skills=[])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="Duplicate Skill id in patch: loadable-skill"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {
                "skills": [
                    {"id": "loadable-skill"},
                    {"id": "loadable-skill"},
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
    )

    class _AgentConfigRepo:
        def get_agent_config(self, _agent_config_id: str):
            return _agent_config(skills=[selected])

        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    with pytest.raises(RuntimeError, match="Library skill not found: loadable-skill"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {"skills": [{"id": "loadable-skill", "enabled": False}]},
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

    with pytest.raises(RuntimeError, match="Skill patch item must use id"):
        agent_user_service.update_agent_user_config(
            "agent-1",
            {
                "skills": [
                    {
                        "skill_id": "missing-skill",
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
                    "id": "loadable-skill",
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


def test_select_agent_skill_uses_agent_config_skill_patch_boundary() -> None:
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

    result = agent_user_service.select_agent_skill(
        "agent-1",
        "loadable-skill",
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
    assert saved_configs[-1].skills[0].description == "loadable"


def test_panel_library_skill_routes_use_skill_repo_without_recipe_repo() -> None:
    app = FastAPI()
    app.include_router(panel_router.router)
    app.dependency_overrides[panel_router.get_current_user_id] = lambda: "owner-1"
    skill_repo = _MemorySkillRepo()
    app.state.runtime_storage_state = _runtime_storage_state(SimpleNamespace(), skill_repo=skill_repo)

    with TestClient(app) as client:
        created = client.post(
            "/api/panel/library/skill",
            json={"name": "Loadable Skill", "desc": "Use this skill", "content": _editable_skill_md()},
        )
        assert created.status_code == 200
        created_id = created.json()["id"]
        assert created_id != "loadable-skill"
        assert created_id.startswith("skill_")

        listed = client.get("/api/panel/library/skill")
        assert listed.status_code == 200
        assert listed.json()["items"][0]["name"] == "Loadable Skill"

        content = client.get(f"/api/panel/library/skill/{created_id}/content")
        assert content.status_code == 200
        assert content.json()["content"] == _editable_skill_md()


def test_library_skill_content_update_rejects_frontmatter_name_drift() -> None:
    skill_repo = _MemorySkillRepo()
    created = library_service.create_resource(
        "skill",
        "Loadable Skill",
        "Use this skill",
        owner_user_id="owner-1",
        skill_repo=skill_repo,
        content=_editable_skill_md(),
    )

    with pytest.raises(ValueError, match="frontmatter name must match Skill name"):
        library_service.update_resource_content(
            "skill",
            created["id"],
            "---\nname: Runtime Skill\ndescription: Use it.\nversion: 1.0.1\n---\n\nUse it.",
            owner_user_id="owner-1",
            skill_repo=skill_repo,
        )

    stored = skill_repo.get_by_id("owner-1", created["id"])
    assert stored is not None and stored.package_id is not None
    assert skill_repo.get_package("owner-1", stored.package_id).skill_md == _editable_skill_md()


def test_library_skill_create_requires_version_frontmatter() -> None:
    skill_repo = _MemorySkillRepo()

    with pytest.raises(ValueError, match="frontmatter version is required"):
        library_service.create_resource(
            "skill",
            "Loadable Skill",
            "Use this skill",
            owner_user_id="owner-1",
            skill_repo=skill_repo,
            content="---\nname: Loadable Skill\ndescription: Use this skill\n---\n\nUse this skill.",
        )

    assert skill_repo.skills == {}
    assert skill_repo.packages == {}


def test_library_skill_content_update_requires_version_frontmatter() -> None:
    skill_repo = _MemorySkillRepo()
    created = library_service.create_resource(
        "skill",
        "Loadable Skill",
        "Use this skill",
        owner_user_id="owner-1",
        skill_repo=skill_repo,
        content=_editable_skill_md(),
    )

    with pytest.raises(ValueError, match="frontmatter version is required"):
        library_service.update_resource_content(
            "skill",
            created["id"],
            "---\nname: Loadable Skill\ndescription: Use this skill\n---\n\nUse it.",
            owner_user_id="owner-1",
            skill_repo=skill_repo,
        )

    stored = skill_repo.get_by_id("owner-1", created["id"])
    assert stored is not None and stored.package_id is not None
    assert skill_repo.get_package("owner-1", stored.package_id).version == "1.0.0"


def test_library_skill_name_is_immutable_after_creation() -> None:
    skill_repo = _MemorySkillRepo()
    created = library_service.create_resource(
        "skill",
        "Loadable Skill",
        "Use this skill",
        owner_user_id="owner-1",
        skill_repo=skill_repo,
        content=_editable_skill_md(),
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


def test_library_skill_create_rejects_duplicate_name_before_write() -> None:
    skill_repo = _MemorySkillRepo()
    created = library_service.create_resource(
        "skill",
        "Loadable Skill",
        "Use this skill",
        owner_user_id="owner-1",
        skill_repo=skill_repo,
        content=_editable_skill_md(),
    )

    with pytest.raises(ValueError, match="Skill name already exists"):
        library_service.create_resource(
            "skill",
            "Loadable Skill",
            "Duplicate name",
            owner_user_id="owner-1",
            skill_repo=skill_repo,
            content=_editable_skill_md("Loadable Skill", "Duplicate name"),
        )

    stored = skill_repo.get_by_id("owner-1", created["id"])
    assert stored is not None
    assert stored.name == "Loadable Skill"
    assert stored.description == "Use this skill"


def test_library_skill_create_does_not_derive_id_from_name() -> None:
    skill_repo = _MemorySkillRepo()

    first = library_service.create_resource(
        "skill",
        "Loadable Skill",
        "Use this skill",
        owner_user_id="owner-1",
        skill_repo=skill_repo,
        content=_editable_skill_md(),
    )
    second = library_service.create_resource(
        "skill",
        "Loadable-Skill",
        "Different name",
        owner_user_id="owner-1",
        skill_repo=skill_repo,
        content=_editable_skill_md("Loadable-Skill", "Different name"),
    )

    assert first["id"] != "loadable-skill"
    assert second["id"] != "loadable-skill"
    assert first["id"] != second["id"]
    assert skill_repo.get_by_id("owner-1", first["id"]).name == "Loadable Skill"
    assert skill_repo.get_by_id("owner-1", second["id"]).name == "Loadable-Skill"


def test_library_skill_create_source_does_not_slugify_name() -> None:
    import inspect

    source = inspect.getsource(library_service.create_resource)

    assert '.lower().replace(" ", "-")' not in source
    assert "generate_skill_id()" in source


def test_library_skill_create_fails_when_generated_id_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    skill_repo = _MemorySkillRepo()
    _put_skill(
        skill_repo,
        owner_user_id="owner-1",
        skill_id="skill_existing",
        name="Existing Skill",
        description="Existing",
        content="---\nname: Existing Skill\nversion: 1.0.0\n---\nExisting.",
    )
    monkeypatch.setattr(library_service, "generate_skill_id", lambda: "skill_existing")

    with pytest.raises(RuntimeError, match="Generated Skill id already exists"):
        library_service.create_resource(
            "skill",
            "Loadable Skill",
            "Use this skill",
            owner_user_id="owner-1",
            skill_repo=skill_repo,
            content=_editable_skill_md(),
        )


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
                skills=[
                    AgentSkill(skill_id="search", package_id="search-package", name="Search", description="repo desc")
                ],
            )

    result = agent_user_service.get_agent_user(
        "agent-1",
        user_repo=SimpleNamespace(get_by_id=lambda user_id: agent if user_id == "agent-1" else None),
        agent_config_repo=_AgentConfigRepo(),
    )

    assert result["config"]["skills"] == [{"id": "search", "name": "Search", "enabled": True, "desc": "repo desc"}]


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
                skills=[
                    AgentSkill(skill_id="search", package_id="search-package", name="Search", description="repo desc")
                ],
            )

    result = agent_user_service.get_agent_user(
        "agent-1",
        user_repo=SimpleNamespace(get_by_id=lambda user_id: agent if user_id == "agent-1" else None),
        agent_config_repo=_AgentConfigRepo(),
    )

    assert result["config"]["skills"] == [{"id": "search", "name": "Search", "enabled": True, "desc": "repo desc"}]


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

    assert result["config"]["skills"] == [{"id": "search", "name": "Search", "enabled": True, "desc": ""}]


def test_apply_snapshot_saves_one_agent_config_aggregate():
    import backend.hub.snapshot_apply as snapshot_apply

    created_users: list[UserRow] = []
    saved_configs: list[AgentConfig] = []
    skill_repo = _MemorySkillRepo()

    class _UserRepo:
        def create(self, row: UserRow) -> None:
            created_users.append(row)

    class _AgentConfigRepo:
        def save_agent_config(self, config: AgentConfig) -> None:
            saved_configs.append(config)

    user_id = snapshot_apply.apply_snapshot(
        snapshot={
            "schema_version": "agent-snapshot/v1",
            "agent": {
                "id": "cfg-source",
                "name": "Repo Agent",
                "description": "Repo desc",
                "model": "leon:large",
                "tools": ["Read"],
                "system_prompt": "main prompt",
                "skills": [
                    {
                        "id": "search-core",
                        "name": "Search",
                        "version": "1.0.0",
                        "content": "---\nname: Search\n---\nbody",
                        "description": "skill desc",
                        "source": {"source_version": "snapshot-stale", "extra": "drop"},
                    }
                ],
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
    assert saved_configs[0].skills[0].skill_id.startswith("skill_")
    assert saved_configs[0].skills[0].skill_id != "search-core"
    assert saved_configs[0].skills[0].package_id
    assert skill_repo.get_by_id("user-1", "search-core") is None
    package = skill_repo.get_package("user-1", saved_configs[0].skills[0].package_id or "")
    assert package is not None
    assert package.skill_md == "---\nname: Search\n---\nbody"
    assert package.source == {
        "marketplace_item_id": "item-1",
        "snapshot_skill_id": "search-core",
        "source_version": "1.0.0",
        "source_at": package.source["source_at"],
    }
    assert "source" not in saved_configs[0].skills[0].model_dump()
    library_skill = skill_repo.get_by_id("user-1", saved_configs[0].skills[0].skill_id)
    assert library_skill is not None
    assert library_skill.source == package.source
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
                    "skills": [{"id": "search", "name": "Search", "version": "1.0.0", "content": "---\nname: Search\n---\nbody"}],
                },
            },
            marketplace_item_id="item-1",
            source_version="1.0.0",
            owner_user_id="user-1",
            user_repo=SimpleNamespace(create=lambda _row: None),
            agent_config_repo=SimpleNamespace(save_agent_config=lambda _config: None),
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("marketplace_item_id", " ", "marketplace_item_id must be a string"),
        ("marketplace_item_id", {"id": "item-1"}, "marketplace_item_id must be a string"),
        ("source_version", " ", "source_version must be a string"),
        ("source_version", ["1.0.0"], "source_version must be a string"),
    ],
)
def test_apply_snapshot_requires_source_identity(field: str, value: object, message: str):
    from backend.hub.snapshot_apply import apply_snapshot

    kwargs = {
        "snapshot": {
            "schema_version": "agent-snapshot/v1",
            "agent": {
                "id": "cfg-source",
                "name": "Repo Agent",
                "skills": [{"id": "search", "name": "Search", "version": "1.0.0", "content": "---\nname: Search\n---\nbody"}],
            },
        },
        "marketplace_item_id": "item-1",
        "source_version": "1.0.0",
        "owner_user_id": "user-1",
        "user_repo": SimpleNamespace(create=lambda _row: None),
        "agent_config_repo": SimpleNamespace(save_agent_config=lambda _config: None),
        "skill_repo": _MemorySkillRepo(),
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match=message):
        apply_snapshot(**cast(Any, kwargs))


def test_apply_snapshot_does_not_fill_package_version_from_source_version() -> None:
    import inspect

    from backend.hub.snapshot_apply import _materialize_snapshot_skills

    source = inspect.getsource(_materialize_snapshot_skills)

    assert "or source_version" not in source


def test_apply_snapshot_generates_library_skill_id() -> None:
    import inspect

    import backend.hub.snapshot_apply as snapshot_apply

    source = inspect.getsource(snapshot_apply)

    assert "_skill_id_from_name" not in source
    assert '.lower().replace(" ", "-")' not in source
    assert "generate_skill_id()" in source
    assert "existing = skill_repo.get_by_id(owner_user_id, skill_id)" not in source


def test_apply_snapshot_source_keeps_snapshot_skill_id_out_of_library_identity() -> None:
    import inspect

    from backend.hub.snapshot_apply import _materialize_snapshot_skills

    source = inspect.getsource(_materialize_snapshot_skills)

    assert "snapshot_skill_id = _required_text(snapshot_skill.id" in source
    assert "skill_id = generate_skill_id()" in source
    assert "skill_id = snapshot_skill_id" not in source
    assert "id=snapshot_skill_id" not in source


def test_apply_snapshot_rejects_duplicate_skill_ids_before_library_write():
    from backend.hub.snapshot_apply import apply_snapshot

    skill_repo = _MemorySkillRepo()

    with pytest.raises(ValueError, match="Duplicate Skill id in snapshot: search"):
        apply_snapshot(
            snapshot={
                "schema_version": "agent-snapshot/v1",
                "agent": {
                    "id": "cfg-source",
                    "name": "Repo Agent",
                    "skills": [
                        {"id": "search", "name": "Search One", "version": "1.0.0", "content": "---\nname: Search One\n---\none"},
                        {"id": "search", "name": "Search Two", "version": "1.0.0", "content": "---\nname: Search Two\n---\ntwo"},
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


def test_apply_snapshot_treats_snapshot_skill_id_as_source_metadata(monkeypatch: pytest.MonkeyPatch):
    from backend.hub.snapshot_apply import apply_snapshot

    skill_repo = _MemorySkillRepo()
    monkeypatch.setattr("backend.hub.snapshot_apply.generate_skill_id", lambda: "skill_generated123")

    saved_configs: list[AgentConfig] = []

    apply_snapshot(
        snapshot={
            "schema_version": "agent-snapshot/v1",
            "agent": {
                "id": "cfg-source",
                "name": "Repo Agent",
                "skills": [
                    {
                        "id": "nested/search",
                        "name": "Search",
                        "version": "1.0.0",
                        "content": "---\nname: Search\n---\nbody",
                    }
                ],
            },
        },
        marketplace_item_id="item-1",
        source_version="1.0.0",
        owner_user_id="user-1",
        user_repo=SimpleNamespace(create=lambda _row: None),
        agent_config_repo=SimpleNamespace(save_agent_config=lambda config: saved_configs.append(config)),
        skill_repo=skill_repo,
    )

    assert saved_configs[0].skills[0].skill_id == "skill_generated123"
    assert skill_repo.get_by_id("user-1", "nested/search") is None
    assert skill_repo.get_by_id("user-1", "skill_generated123") is not None
    package = skill_repo.get_package("user-1", saved_configs[0].skills[0].package_id)
    assert package is not None
    assert package.source["snapshot_skill_id"] == "nested/search"


def test_apply_snapshot_reuses_existing_skill_by_snapshot_source(monkeypatch: pytest.MonkeyPatch):
    from backend.hub.snapshot_apply import apply_snapshot

    skill_repo = _MemorySkillRepo()
    timestamp = datetime(2026, 4, 24, tzinfo=UTC)
    skill_repo.upsert(
        Skill(
            id="skill_existing123",
            owner_user_id="user-1",
            name="Search",
            description="old",
            source={"marketplace_item_id": "item-1", "snapshot_skill_id": "search-core"},
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    monkeypatch.setattr(
        "backend.hub.snapshot_apply.generate_skill_id",
        lambda: (_ for _ in ()).throw(AssertionError("must reuse the source Skill")),
    )
    saved_configs: list[AgentConfig] = []

    apply_snapshot(
        snapshot={
            "schema_version": "agent-snapshot/v1",
            "agent": {
                "id": "cfg-source",
                "name": "Repo Agent",
                "skills": [{"id": "search-core", "name": "Search", "version": "1.0.1", "content": "---\nname: Search\n---\nnew"}],
            },
        },
        marketplace_item_id="item-1",
        source_version="1.0.1",
        owner_user_id="user-1",
        user_repo=SimpleNamespace(create=lambda _row: None),
        agent_config_repo=SimpleNamespace(save_agent_config=lambda config: saved_configs.append(config)),
        skill_repo=skill_repo,
    )

    assert saved_configs[0].skills[0].skill_id == "skill_existing123"
    assert skill_repo.get_by_id("user-1", "skill_existing123").description == ""
    package = skill_repo.get_package("user-1", saved_configs[0].skills[0].package_id)
    assert package is not None
    assert package.source["snapshot_skill_id"] == "search-core"


def test_apply_snapshot_fails_when_generated_skill_id_exists(monkeypatch: pytest.MonkeyPatch):
    from backend.hub.snapshot_apply import apply_snapshot

    skill_repo = _MemorySkillRepo()
    _put_skill(
        skill_repo,
        owner_user_id="user-1",
        skill_id="skill_existing123",
        name="Existing",
        description="existing",
        content="---\nname: Existing\n---\nbody",
    )
    monkeypatch.setattr("backend.hub.snapshot_apply.generate_skill_id", lambda: "skill_existing123")

    with pytest.raises(RuntimeError, match="Generated Skill id already exists"):
        apply_snapshot(
            snapshot={
                "schema_version": "agent-snapshot/v1",
                "agent": {
                    "id": "cfg-source",
                    "name": "Repo Agent",
                    "skills": [{"id": "search-core", "name": "Search", "version": "1.0.0", "content": "---\nname: Search\n---\nbody"}],
                },
            },
            marketplace_item_id="item-1",
            source_version="1.0.0",
            owner_user_id="user-1",
            user_repo=SimpleNamespace(create=lambda _row: None),
            agent_config_repo=SimpleNamespace(save_agent_config=lambda _config: None),
            skill_repo=skill_repo,
        )


def test_apply_snapshot_rejects_existing_same_name_without_snapshot_source(monkeypatch: pytest.MonkeyPatch):
    from backend.hub.snapshot_apply import apply_snapshot

    skill_repo = _MemorySkillRepo()
    _put_skill(
        skill_repo,
        owner_user_id="user-1",
        skill_id="skill_existing123",
        name="Search",
        description="existing",
        content="---\nname: Search\n---\nbody",
    )
    monkeypatch.setattr("backend.hub.snapshot_apply.generate_skill_id", lambda: "skill_generated123")

    with pytest.raises(ValueError, match="Snapshot Skill name already exists under a different Library id"):
        apply_snapshot(
            snapshot={
                "schema_version": "agent-snapshot/v1",
                "agent": {
                    "id": "cfg-source",
                    "name": "Repo Agent",
                    "skills": [{"id": "search-core", "name": "Search", "version": "1.0.0", "content": "---\nname: Search\n---\nbody"}],
                },
            },
            marketplace_item_id="item-1",
            source_version="1.0.0",
            owner_user_id="user-1",
            user_repo=SimpleNamespace(create=lambda _row: None),
            agent_config_repo=SimpleNamespace(save_agent_config=lambda _config: None),
            skill_repo=skill_repo,
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
                        {"id": "search-one", "name": "Search", "version": "1.0.0", "content": "---\nname: Search\n---\none"},
                        {"id": "search-two", "name": "Search", "version": "1.0.0", "content": "---\nname: Search\n---\ntwo"},
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
