from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.web.models.marketplace import (
    ApplyFromMarketplaceRequest,
    PublishAgentUserToMarketplaceRequest,
    UpgradeFromMarketplaceRequest,
)
from backend.web.routers import marketplace as marketplace_router
from backend.web.routers import panel as panel_router
from config.agent_config_types import AgentConfig
from storage.contracts import UserRow, UserType


def _runtime_storage_state(agent_config_repo: object, skill_repo: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        storage_container=SimpleNamespace(
            agent_config_repo=lambda: agent_config_repo,
            skill_repo=lambda: skill_repo,
        )
    )


def _agent_config(**updates: object) -> AgentConfig:
    data = {
        "id": "cfg-1",
        "owner_user_id": "owner-1",
        "agent_user_id": "agent-1",
        "name": "Demo Agent",
        "description": "probe",
        "tools": ["*"],
        "system_prompt": "hello",
        "status": "draft",
        "version": "0.1.0",
        "runtime_settings": {},
        "compact": {},
        "skills": [],
        "rules": [],
        "sub_agents": [],
        "mcp_servers": [],
        "meta": {},
    }
    data.update(updates)
    return AgentConfig(**data)


def test_marketplace_router_exposes_agent_user_marketplace_routes() -> None:
    paths = {getattr(route, "path", "") for route in marketplace_router.router.routes}

    assert "/api/marketplace/publish-agent-user" in paths
    assert "/api/marketplace/items" in paths
    assert "/api/marketplace/items/{item_id}" in paths
    assert "/api/marketplace/items/{item_id}/lineage" in paths
    assert "/api/marketplace/items/{item_id}/versions/{version}" in paths
    assert "/api/marketplace/apply" in paths
    assert "/api/marketplace/" + "download" not in paths


def test_skill_marketplace_to_agent_library_delete_backend_api_yatu(monkeypatch: pytest.MonkeyPatch) -> None:
    class _SkillRepo:
        def __init__(self) -> None:
            self.skills: dict[tuple[str, str], Any] = {}
            self.packages: dict[tuple[str, str], Any] = {}

        def list_for_owner(self, owner_user_id: str) -> list[Any]:
            return [skill for (owner, _), skill in self.skills.items() if owner == owner_user_id]

        def get_by_id(self, owner_user_id: str, skill_id: str) -> Any | None:
            return self.skills.get((owner_user_id, skill_id))

        def upsert(self, skill: Any) -> Any:
            self.skills[(getattr(skill, "owner_user_id"), getattr(skill, "id"))] = skill
            return skill

        def create_package(self, package: Any) -> Any:
            self.packages[(getattr(package, "owner_user_id"), getattr(package, "id"))] = package
            return package

        def get_package(self, owner_user_id: str, package_id: str) -> Any | None:
            return self.packages.get((owner_user_id, package_id))

        def select_package(self, owner_user_id: str, skill_id: str, package_id: str) -> None:
            skill = self.skills[(owner_user_id, skill_id)]
            self.skills[(owner_user_id, skill_id)] = skill.model_copy(update={"package_id": package_id})

        def delete(self, owner_user_id: str, skill_id: str) -> None:
            self.skills.pop((owner_user_id, skill_id), None)

    class _UserRepo:
        def __init__(self) -> None:
            self.agent = UserRow(
                id="agent-1",
                type=UserType.AGENT,
                display_name="Demo Agent",
                owner_user_id="owner-1",
                agent_config_id="cfg-1",
                created_at=1.0,
            )

        def get_by_id(self, user_id: str) -> Any | None:
            if user_id == "agent-1":
                return self.agent
            return None

        def list_by_owner_user_id(self, owner_user_id: str) -> list[Any]:
            return [self.agent] if owner_user_id == "owner-1" else []

    class _AgentConfigRepo:
        def __init__(self) -> None:
            self.config = _agent_config()

        def get_agent_config(self, agent_config_id: str) -> AgentConfig | None:
            return self.config if agent_config_id == "cfg-1" else None

        def save_agent_config(self, config: AgentConfig) -> None:
            self.config = config

    def hub_response(_method: str, path: str, **_kwargs: object) -> dict[str, object]:
        item_id = path.removeprefix("/items/").removesuffix("/download")
        rows = {
            "skillsmp:alpha": {
                "slug": "alpha-skill",
                "name": "Alpha Skill",
                "description": "Alpha desc",
                "body": "Use alpha routing.",
            },
            "skillsmp:beta": {
                "slug": "beta-skill",
                "name": "Beta Skill",
                "description": "Beta desc",
                "body": "Use beta routing.",
            },
        }
        row = rows[item_id]
        return {
            "item": {
                "type": "skill",
                "slug": row["slug"],
                "name": row["name"],
                "description": row["description"],
                "publisher_username": "skillsmp",
            },
            "version": "1.0.0",
            "snapshot": {
                "content": f"---\nname: {row['name']}\n---\n{row['body']}",
                "meta": {"desc": row["description"]},
                "files": {"references/routing.md": row["body"]},
            },
        }

    monkeypatch.setattr(marketplace_router.marketplace_client, "_hub_api", hub_response)

    app = FastAPI()
    app.include_router(marketplace_router.router)
    app.include_router(panel_router.router)
    app.dependency_overrides[marketplace_router.get_current_user_id] = lambda: "owner-1"
    app.dependency_overrides[panel_router.get_current_user_id] = lambda: "owner-1"
    user_repo = _UserRepo()
    agent_config_repo = _AgentConfigRepo()
    skill_repo = _SkillRepo()
    app.state.user_repo = user_repo
    app.state.runtime_storage_state = _runtime_storage_state(agent_config_repo, skill_repo)

    with TestClient(app) as client:
        alpha_apply = client.post("/api/marketplace/apply", json={"item_id": "skillsmp:alpha", "agent_user_id": "agent-1"})
        beta_apply = client.post("/api/marketplace/apply", json={"item_id": "skillsmp:beta"})
        library_after_apply = client.get("/api/panel/library/skill")
        agent_after_apply = client.get("/api/panel/agents/agent-1")

        assign_both = client.put(
            "/api/panel/agents/agent-1/config",
            json={"skills": [{"name": "Alpha Skill", "enabled": True}, {"name": "Beta Skill", "enabled": True}]},
        )
        blocked_alpha_delete = client.delete("/api/panel/library/skill/alpha-skill")

        keep_beta = client.put("/api/panel/agents/agent-1/config", json={"skills": [{"name": "Beta Skill", "enabled": True}]})
        deleted_alpha = client.delete("/api/panel/library/skill/alpha-skill")
        blocked_beta_delete = client.delete("/api/panel/library/skill/beta-skill")

        clear_skills = client.put("/api/panel/agents/agent-1/config", json={"skills": []})
        deleted_beta = client.delete("/api/panel/library/skill/beta-skill")
        library_after_delete = client.get("/api/panel/library/skill")

    assert alpha_apply.status_code == 200
    assert alpha_apply.json()["agent_user_id"] == "agent-1"
    assert beta_apply.status_code == 200
    assert sorted(item["name"] for item in library_after_apply.json()["items"]) == ["Alpha Skill", "Beta Skill"]
    assert agent_after_apply.status_code == 200
    assert [item["name"] for item in agent_after_apply.json()["config"]["skills"]] == ["Alpha Skill"]
    assert assign_both.status_code == 200
    assert [item["name"] for item in assign_both.json()["config"]["skills"]] == ["Alpha Skill", "Beta Skill"]
    assert blocked_alpha_delete.status_code == 409
    assert blocked_alpha_delete.json()["detail"] == "Skill is still assigned to Agent: Demo Agent"
    assert keep_beta.status_code == 200
    assert deleted_alpha.status_code == 200
    assert blocked_beta_delete.status_code == 409
    assert clear_skills.status_code == 200
    assert deleted_beta.status_code == 200
    assert library_after_delete.status_code == 200
    assert library_after_delete.json()["items"] == []


@pytest.mark.asyncio
async def test_publish_agent_user_to_marketplace_uses_user_repo_not_member_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setattr(marketplace_router.marketplace_client, "publish", lambda **kwargs: seen.update(kwargs) or {"ok": True})
    monkeypatch.setattr(
        "backend.identity.profile.get_profile",
        lambda user=None: (
            (_ for _ in ()).throw(AssertionError("profile lookup must be user-scoped")) if user is None else {"name": user.display_name}
        ),
    )

    user_repo = SimpleNamespace(
        get_by_id=lambda user_id: (
            SimpleNamespace(id=user_id, owner_user_id="owner-1")
            if user_id == "agent-1"
            else SimpleNamespace(id=user_id, display_name="owner-name", email="owner@example.com")
            if user_id == "owner-1"
            else None
        )
    )
    agent_config_repo = SimpleNamespace()
    req = PublishAgentUserToMarketplaceRequest(user_id="agent-1")
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                user_repo=user_repo,
                runtime_storage_state=_runtime_storage_state(agent_config_repo),
            )
        )
    )

    result = await marketplace_router.publish_agent_user_to_marketplace(req=req, user_id="owner-1", request=cast(Any, request))

    assert result == {"ok": True}
    assert seen["user_id"] == "agent-1"
    assert seen["type_"] == "member"
    assert seen["publisher_user_id"] == "owner-1"
    assert seen["publisher_username"] == "owner-name"
    assert seen["user_repo"] is user_repo
    assert seen["agent_config_repo"] is agent_config_repo


@pytest.mark.asyncio
async def test_upgrade_from_marketplace_uses_user_repo_not_member_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setattr(marketplace_router.marketplace_client, "upgrade", lambda **kwargs: seen.update(kwargs) or {"ok": True})

    req = UpgradeFromMarketplaceRequest(user_id="agent-1", item_id="item-1")
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                user_repo=SimpleNamespace(
                    get_by_id=lambda user_id: SimpleNamespace(id=user_id, owner_user_id="owner-1") if user_id == "agent-1" else None
                ),
                runtime_storage_state=_runtime_storage_state(SimpleNamespace()),
            )
        )
    )

    result = await marketplace_router.upgrade_from_marketplace(req=req, user_id="owner-1", request=cast(Any, request))

    assert result == {"ok": True}
    assert seen["user_id"] == "agent-1"
    assert seen["item_id"] == "item-1"
    assert seen["owner_user_id"] == "owner-1"
    assert seen["user_repo"] is request.app.state.user_repo
    assert seen["agent_config_repo"] is request.app.state.runtime_storage_state.storage_container.agent_config_repo()
    assert seen["skill_repo"] is request.app.state.runtime_storage_state.storage_container.skill_repo()


@pytest.mark.asyncio
async def test_apply_marketplace_item_uses_user_and_agent_config_repos(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setattr(marketplace_router.marketplace_client, "apply_item", lambda **kwargs: seen.update(kwargs) or {"ok": True})

    owner_agent = SimpleNamespace(id="agent-1", owner_user_id="owner-1")
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                user_repo=SimpleNamespace(get_by_id=lambda user_id: owner_agent if user_id == "agent-1" else None),
                runtime_storage_state=_runtime_storage_state(SimpleNamespace()),
            )
        )
    )
    req = ApplyFromMarketplaceRequest(item_id="item-1", agent_user_id="agent-1")

    result = await marketplace_router.apply_marketplace_item(req=req, user_id="owner-1", request=cast(Any, request))

    assert result == {"ok": True}
    assert seen["item_id"] == "item-1"
    assert seen["owner_user_id"] == "owner-1"
    assert seen["user_repo"] is request.app.state.user_repo
    assert seen["agent_config_repo"] is request.app.state.runtime_storage_state.storage_container.agent_config_repo()
    assert seen["skill_repo"] is request.app.state.runtime_storage_state.storage_container.skill_repo()
    assert seen["agent_user_id"] == "agent-1"


@pytest.mark.asyncio
async def test_apply_member_snapshot_materializes_skill_through_router(monkeypatch: pytest.MonkeyPatch) -> None:
    class _SkillRepo:
        def __init__(self) -> None:
            self.skills: dict[tuple[str, str], Any] = {}
            self.packages: dict[tuple[str, str], Any] = {}

        def list_for_owner(self, owner_user_id: str) -> list[Any]:
            return [skill for (owner, _), skill in self.skills.items() if owner == owner_user_id]

        def get_by_id(self, owner_user_id: str, skill_id: str) -> Any | None:
            return self.skills.get((owner_user_id, skill_id))

        def upsert(self, skill: Any) -> Any:
            self.skills[(getattr(skill, "owner_user_id"), getattr(skill, "id"))] = skill
            return skill

        def create_package(self, package: Any) -> Any:
            self.packages[(getattr(package, "owner_user_id"), getattr(package, "id"))] = package
            return package

        def get_package(self, owner_user_id: str, package_id: str) -> Any | None:
            return self.packages.get((owner_user_id, package_id))

        def select_package(self, owner_user_id: str, skill_id: str, package_id: str) -> None:
            skill = self.skills[(owner_user_id, skill_id)]
            self.skills[(owner_user_id, skill_id)] = skill.model_copy(update={"package_id": package_id})

    class _UserRepo:
        def __init__(self) -> None:
            self.users: dict[str, Any] = {}

        def get_by_id(self, user_id: str) -> Any | None:
            return self.users.get(user_id)

        def create(self, row: Any) -> None:
            self.users[getattr(row, "id")] = row

    class _AgentConfigRepo:
        def __init__(self) -> None:
            self.saved: list[Any] = []

        def save_agent_config(self, config: Any) -> None:
            self.saved.append(config)

    def hub_response(_method: str, _path: str, **_kwargs: object) -> dict[str, object]:
        return {
            "item": {"type": "member", "name": "Snapshot Agent"},
            "version": "1.2.3",
            "snapshot": {
                "schema_version": "agent-snapshot/v1",
                "agent": {
                    "id": "source-cfg",
                    "name": "Snapshot Agent",
                    "skills": [
                        {
                            "name": "Snapshot Skill",
                            "description": "skill desc",
                            "version": "1.2.3",
                            "content": "---\nname: Snapshot Skill\n---\nbody",
                            "files": {"references/routing.md": "route narrowly"},
                        }
                    ],
                },
            },
        }

    monkeypatch.setattr(marketplace_router.marketplace_client, "_hub_api", hub_response)
    skill_repo = _SkillRepo()
    agent_config_repo = _AgentConfigRepo()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                user_repo=_UserRepo(),
                runtime_storage_state=_runtime_storage_state(agent_config_repo, skill_repo),
            )
        )
    )

    result = await marketplace_router.apply_marketplace_item(
        req=ApplyFromMarketplaceRequest(item_id="item-1"),
        user_id="owner-1",
        request=cast(Any, request),
    )

    saved_config = agent_config_repo.saved[0]
    saved_skill = saved_config.skills[0]
    assert result == {"user_id": saved_config.agent_user_id, "type": "user", "version": "1.2.3"}
    assert saved_skill.skill_id == "snapshot-skill"
    assert saved_skill.package_id
    package = skill_repo.get_package("owner-1", saved_skill.package_id)
    assert package is not None
    assert getattr(package, "files") == {"references/routing.md": "route narrowly"}


@pytest.mark.asyncio
async def test_apply_marketplace_item_maps_semantic_rejections_to_400(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(**_kwargs: object) -> dict[str, object]:
        raise ValueError("Skill snapshot frontmatter name must match existing Skill name")

    monkeypatch.setattr(marketplace_router.marketplace_client, "apply_item", reject)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                user_repo=SimpleNamespace(get_by_id=lambda _user_id: None),
                runtime_storage_state=_runtime_storage_state(SimpleNamespace()),
            )
        )
    )
    req = ApplyFromMarketplaceRequest(item_id="item-1")

    with pytest.raises(HTTPException) as exc_info:
        await marketplace_router.apply_marketplace_item(req=req, user_id="owner-1", request=cast(Any, request))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Skill snapshot frontmatter name must match existing Skill name"


@pytest.mark.asyncio
async def test_list_marketplace_items_reads_hub_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        marketplace_router.marketplace_client,
        "list_items",
        lambda **kwargs: seen.update(kwargs) or {"items": [{"id": "item-1"}], "total": 1},
        raising=False,
    )

    result = await marketplace_router.list_marketplace_items(
        type="skill",
        q="search",
        sort="newest",
        page=2,
        page_size=10,
    )

    assert result == {"items": [{"id": "item-1"}], "total": 1}
    assert seen == {"type": "skill", "q": "search", "sort": "newest", "page": 2, "page_size": 10}


@pytest.mark.asyncio
async def test_get_marketplace_item_detail_reads_hub_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        marketplace_router.marketplace_client,
        "get_item_detail",
        lambda item_id: {"id": item_id, "name": "Hub Item"},
        raising=False,
    )

    result = await marketplace_router.get_marketplace_item_detail("item-1")

    assert result == {"id": "item-1", "name": "Hub Item"}


@pytest.mark.asyncio
async def test_get_marketplace_item_lineage_reads_hub_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        marketplace_router.marketplace_client,
        "get_item_lineage",
        lambda item_id: {"ancestors": [], "children": [{"id": item_id}]},
        raising=False,
    )

    result = await marketplace_router.get_marketplace_item_lineage("item-1")

    assert result == {"ancestors": [], "children": [{"id": "item-1"}]}


@pytest.mark.asyncio
async def test_get_marketplace_item_version_snapshot_reads_hub_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        marketplace_router.marketplace_client,
        "get_item_version_snapshot",
        lambda item_id, version: {"snapshot": {"meta": {"id": item_id, "version": version}}},
        raising=False,
    )

    result = await marketplace_router.get_marketplace_item_version_snapshot("item-1", "1.2.3")

    assert result == {"snapshot": {"meta": {"id": "item-1", "version": "1.2.3"}}}


@pytest.mark.asyncio
async def test_get_marketplace_item_detail_preserves_hub_http_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        marketplace_router.marketplace_client,
        "get_item_detail",
        lambda _item_id: (_ for _ in ()).throw(HTTPException(status_code=404, detail="Marketplace item not found")),
        raising=False,
    )

    with pytest.raises(HTTPException) as exc_info:
        await marketplace_router.get_marketplace_item_detail("missing-item")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Marketplace item not found"


@pytest.mark.asyncio
async def test_list_marketplace_items_preserves_hub_http_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        marketplace_router.marketplace_client,
        "list_items",
        lambda **_kwargs: (_ for _ in ()).throw(HTTPException(status_code=400, detail="Unsupported sort: featured")),
        raising=False,
    )

    with pytest.raises(HTTPException) as exc_info:
        await marketplace_router.list_marketplace_items(sort="featured")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Unsupported sort: featured"


@pytest.mark.asyncio
async def test_verify_user_ownership_raises_when_user_repo_row_not_owned() -> None:
    user_repo = SimpleNamespace(get_by_id=lambda _user_id: SimpleNamespace(id="agent-1", owner_user_id="owner-2"))

    with pytest.raises(HTTPException) as exc_info:
        await marketplace_router._verify_user_ownership("agent-1", "owner-1", user_repo)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Not authorized to publish this user"
