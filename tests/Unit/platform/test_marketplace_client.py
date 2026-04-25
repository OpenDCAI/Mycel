"""Tests for marketplace_client business logic (publish/apply)."""

import importlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException

from backend.hub.versioning import bump_semver
from config.agent_config_types import AgentConfig, AgentRule, AgentSkill, AgentSubAgent, McpServerConfig, Skill, SkillPackage

# ── Version Bump (tested via publish internals) ──


class TestVersionBump:
    def test_patch_bump(self):
        assert bump_semver("1.2.3", "patch") == "1.2.4"

    def test_minor_bump(self):
        assert bump_semver("1.2.3", "minor") == "1.3.0"

    def test_major_bump(self):
        assert bump_semver("1.2.3", "major") == "2.0.0"

    def test_initial_version(self):
        assert bump_semver("0.1.0", "patch") == "0.1.1"


# ── Hub client contract ──


def test_hub_client_disables_env_proxy_trust():
    import backend.hub.client as marketplace_client

    marketplace_client = importlib.reload(marketplace_client)

    assert marketplace_client._hub_client._trust_env is False


def test_hub_client_defaults_to_public_mycel_hub(monkeypatch):
    monkeypatch.delenv("MYCEL_HUB_URL", raising=False)

    import backend.hub.client as marketplace_client

    marketplace_client = importlib.reload(marketplace_client)

    assert marketplace_client.HUB_URL == "https://hub.mycel.nextmind.space"


def test_hub_api_preserves_hub_bad_request_detail(monkeypatch):
    import backend.hub.client as marketplace_client

    class _Response:
        status_code = 400

        def raise_for_status(self):
            request = httpx.Request("GET", "http://hub/api/v1/items")
            response = httpx.Response(400, json={"detail": "Unsupported sort: featured"}, request=request)
            raise httpx.HTTPStatusError("bad request", request=request, response=response)

    monkeypatch.setattr(marketplace_client._hub_client, "request", lambda *_args, **_kwargs: _Response())

    with pytest.raises(HTTPException) as exc_info:
        marketplace_client._hub_api("GET", "/items")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Unsupported sort: featured"


# ── Helpers ──


def _make_hub_response(item_type: str, slug: str, content: str = "# Hello", version: str = "1.0.0", publisher: str = "tester") -> dict:
    """Build a fake Hub /download response."""
    return {
        "item": {
            "name": slug.replace("-", " ").title(),
            "slug": slug,
            "type": item_type,
            "description": "A test item",
            "tags": ["test"],
            "publisher_username": publisher,
        },
        "snapshot": {
            "content": content,
            "meta": {"name": slug.replace("-", " ").title(), "desc": "A test item"},
        },
        "version": version,
    }


def _agent_config(**overrides: object) -> AgentConfig:
    data = {
        "id": "cfg-1",
        "owner_user_id": "owner-1",
        "agent_user_id": "agent-user-1",
        "name": "Repo Agent",
        "description": "from repo",
        "tools": ["search"],
        "system_prompt": "be helpful",
        "status": "draft",
        "version": "0.1.0",
        "runtime_settings": {"tools:search": {"enabled": True, "desc": "Search"}},
        "meta": {"source": {"marketplace_item_id": "item-parent", "source_version": "0.1.0"}},
        "mcp_servers": [McpServerConfig(name="demo", transport="stdio", command="demo")],
    }
    data.update(overrides)
    return AgentConfig(**data)


# ── Apply — skill ──


class TestApplySkill:
    def test_writes_skill_to_skill_repo(self, monkeypatch):
        monkeypatch.setattr("backend.hub.client.generate_skill_id", lambda: "skill_generated123")
        saved: list[Skill] = []
        packages: list[SkillPackage] = []
        selected: list[tuple[str, str, str]] = []
        hub_resp = _make_hub_response("skill", "my-skill", content="---\nname: My Skill\n---\n# My Skill\nDo stuff")
        hub_resp["snapshot"]["files"] = {"references/usage.md": "Use carefully"}
        skill_repo = SimpleNamespace(
            get_by_id=lambda _owner_user_id, _skill_id: None,
            list_for_owner=lambda _owner_user_id: [],
            upsert=lambda skill: saved.append(skill) or skill,
            create_package=lambda package: packages.append(package) or package,
            select_package=lambda owner_user_id, skill_id, package_id: selected.append((owner_user_id, skill_id, package_id)),
        )

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            from backend.hub.client import apply_item

            result = apply_item("item-123", owner_user_id="owner-1", skill_repo=skill_repo)

        assert result["type"] == "skill"
        assert result["resource_id"] == "skill_generated123"
        assert saved[0].id == "skill_generated123"
        assert saved[0].owner_user_id == "owner-1"
        assert saved[0].name == "My Skill"
        assert not hasattr(saved[0], "content")
        assert packages[0].skill_id == "skill_generated123"
        assert packages[0].skill_md == "---\nname: My Skill\n---\n# My Skill\nDo stuff"
        assert packages[0].manifest["files"][0]["path"] == "references/usage.md"
        assert selected == [("owner-1", "skill_generated123", packages[0].id)]
        assert result["package_id"] == packages[0].id

    def test_apply_skill_does_not_use_hub_slug_as_library_id(self) -> None:
        import inspect

        import backend.hub.client as marketplace_client

        source = inspect.getsource(marketplace_client.apply_item)

        assert "id=slug" not in source
        assert "get_by_id(owner_user_id, slug)" not in source

    def test_writes_hub_skill_files_as_posix_paths(self):
        saved: list[Skill] = []
        packages: list[SkillPackage] = []
        hub_resp = _make_hub_response("skill", "my-skill", content="---\nname: My Skill\n---\n# My Skill\nDo stuff")
        hub_resp["snapshot"]["files"] = {"references\\usage.md": "Use carefully"}
        skill_repo = SimpleNamespace(
            get_by_id=lambda _owner_user_id, _skill_id: None,
            list_for_owner=lambda _owner_user_id: [],
            upsert=lambda skill: saved.append(skill) or skill,
            create_package=lambda package: packages.append(package) or package,
            select_package=lambda _owner_user_id, _skill_id, _package_id: None,
        )

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            from backend.hub.client import apply_item

            apply_item("item-123", owner_user_id="owner-1", skill_repo=skill_repo)

        assert saved[0].id == "my-skill"
        assert packages[0].manifest["files"][0]["path"] == "references/usage.md"

    def test_apply_rejects_hub_skill_file_path_collision(self):
        saved: list[Skill] = []
        hub_resp = _make_hub_response("skill", "my-skill", content="---\nname: My Skill\n---\n# My Skill\nDo stuff")
        hub_resp["snapshot"]["files"] = {
            "references\\usage.md": "Windows-shaped key.",
            "references/usage.md": "POSIX-shaped key.",
        }
        skill_repo = SimpleNamespace(
            get_by_id=lambda _owner_user_id, _skill_id: None,
            list_for_owner=lambda _owner_user_id: [],
            upsert=lambda skill: saved.append(skill) or skill,
        )

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            from backend.hub.client import apply_item

            with pytest.raises(ValueError, match="Skill snapshot files contain duplicate path after normalization: references/usage.md"):
                apply_item("item-123", owner_user_id="owner-1", skill_repo=skill_repo)

        assert saved == []

    def test_skill_repo_payload_has_source_tracking(self):
        saved: list[Skill] = []
        packages: list[SkillPackage] = []
        hub_resp = _make_hub_response(
            "skill", "tracked-skill", content="---\nname: Tracked Skill\n---\n# Hello", version="2.1.0", publisher="alice"
        )
        skill_repo = SimpleNamespace(
            get_by_id=lambda _owner_user_id, _skill_id: None,
            list_for_owner=lambda _owner_user_id: [],
            upsert=lambda skill: saved.append(skill) or skill,
            create_package=lambda package: packages.append(package) or package,
            select_package=lambda _owner_user_id, _skill_id, _package_id: None,
        )

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            from backend.hub.client import apply_item

            apply_item("item-456", owner_user_id="owner-1", skill_repo=skill_repo)

        assert saved[0].source["marketplace_item_id"] == "item-456"
        assert saved[0].source["source_version"] == "2.1.0"
        assert saved[0].source["publisher"] == "alice"
        assert packages[0].source["source_version"] == "2.1.0"

    def test_apply_skill_uses_frontmatter_description_as_library_description(self):
        saved: list[Skill] = []
        packages: list[SkillPackage] = []
        hub_resp = _make_hub_response(
            "skill",
            "described-skill",
            content="---\nname: Described Skill\ndescription: Frontmatter description\n---\n# Hello",
        )
        hub_resp["item"]["description"] = "Hub card description"
        hub_resp["snapshot"]["meta"]["desc"] = "Snapshot meta description"
        skill_repo = SimpleNamespace(
            get_by_id=lambda _owner_user_id, _skill_id: None,
            list_for_owner=lambda _owner_user_id: [],
            upsert=lambda skill: saved.append(skill) or skill,
            create_package=lambda package: packages.append(package) or package,
            select_package=lambda _owner_user_id, _skill_id, _package_id: None,
        )

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            from backend.hub.client import apply_item

            apply_item("item-described", owner_user_id="owner-1", skill_repo=skill_repo)

        assert saved[0].description == "Frontmatter description"

    def test_apply_skill_requires_snapshot_version(self):
        hub_resp = _make_hub_response("skill", "broken-skill", content="---\nname: Broken Skill\ndescription: Broken\n---\nBody")
        del hub_resp["version"]
        skill_repo = SimpleNamespace(
            get_by_id=lambda _owner_user_id, _skill_id: None,
            list_for_owner=lambda _owner_user_id: [],
            upsert=lambda _skill: (_ for _ in ()).throw(AssertionError("must not save broken Skill")),
        )

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            from backend.hub.client import apply_item

            with pytest.raises(ValueError, match="Hub download version must be a string"):
                apply_item("item-broken", owner_user_id="owner-1", skill_repo=skill_repo)

    def test_apply_skill_does_not_require_item_slug(self, monkeypatch):
        monkeypatch.setattr("backend.hub.client.generate_skill_id", lambda: "skill_noSlug123")
        hub_resp = _make_hub_response("skill", "broken-skill", content="---\nname: Broken Skill\ndescription: Broken\n---\nBody")
        del hub_resp["item"]["slug"]
        saved: list[Skill] = []
        packages: list[SkillPackage] = []
        skill_repo = SimpleNamespace(
            get_by_id=lambda _owner_user_id, _skill_id: None,
            list_for_owner=lambda _owner_user_id: [],
            upsert=lambda skill: saved.append(skill) or skill,
            create_package=lambda package: packages.append(package) or package,
            select_package=lambda _owner_user_id, _skill_id, _package_id: None,
        )

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            from backend.hub.client import apply_item

            result = apply_item("item-broken", owner_user_id="owner-1", skill_repo=skill_repo)

        assert result["resource_id"] == "skill_noSlug123"
        assert saved[0].id == "skill_noSlug123"

    def test_apply_skill_requires_publisher(self):
        hub_resp = _make_hub_response("skill", "broken-skill", content="---\nname: Broken Skill\ndescription: Broken\n---\nBody")
        del hub_resp["item"]["publisher_username"]
        skill_repo = SimpleNamespace(
            get_by_id=lambda _owner_user_id, _skill_id: None,
            list_for_owner=lambda _owner_user_id: [],
            upsert=lambda _skill: (_ for _ in ()).throw(AssertionError("must not save broken Skill")),
        )

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            from backend.hub.client import apply_item

            with pytest.raises(ValueError, match="Hub item publisher_username must be a string"):
                apply_item("item-broken", owner_user_id="owner-1", skill_repo=skill_repo)

    def test_apply_to_library_rejects_name_drift_for_existing_skill_id(self):
        existing = Skill(
            id="same-slug",
            owner_user_id="owner-1",
            name="Original Skill",
            created_at=datetime(2026, 4, 24, tzinfo=UTC),
            updated_at=datetime(2026, 4, 24, tzinfo=UTC),
        )
        hub_resp = _make_hub_response("skill", "same-slug", content="---\nname: Renamed Skill\n---\nBody")
        skill_repo = SimpleNamespace(
            get_by_id=lambda owner_user_id, skill_id: existing if (owner_user_id, skill_id) == ("owner-1", "same-slug") else None,
            upsert=lambda _skill: (_ for _ in ()).throw(AssertionError("must not rename existing Skill")),
        )

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            from backend.hub.client import apply_item

            with pytest.raises(ValueError, match="frontmatter name must match existing Skill name"):
                apply_item("item-rename", owner_user_id="owner-1", skill_repo=skill_repo)

    def test_apply_to_library_rejects_same_name_under_different_skill_id(self):
        existing = Skill(
            id="original-slug",
            owner_user_id="owner-1",
            name="Shared Name",
            created_at=datetime(2026, 4, 24, tzinfo=UTC),
            updated_at=datetime(2026, 4, 24, tzinfo=UTC),
        )
        hub_resp = _make_hub_response("skill", "new-slug", content="---\nname: Shared Name\n---\nBody")
        skill_repo = SimpleNamespace(
            get_by_id=lambda _owner_user_id, _skill_id: None,
            list_for_owner=lambda _owner_user_id: [existing],
            upsert=lambda _skill: (_ for _ in ()).throw(AssertionError("must not create a second id for the same Skill name")),
        )

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            from backend.hub.client import apply_item

            with pytest.raises(ValueError, match="Skill name already exists under a different Library id"):
                apply_item("item-duplicate-name", owner_user_id="owner-1", skill_repo=skill_repo)

    def test_apply_to_library_rejects_invalid_skill_frontmatter_yaml(self):
        hub_resp = _make_hub_response("skill", "broken-skill", content="---\nname: [broken\n---\nBody")
        skill_repo = SimpleNamespace(
            get_by_id=lambda _owner_user_id, _skill_id: None,
            list_for_owner=lambda _owner_user_id: [],
            upsert=lambda _skill: (_ for _ in ()).throw(AssertionError("must not save broken Skill")),
        )

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            from backend.hub.client import apply_item

            with pytest.raises(ValueError, match="Skill snapshot frontmatter must be valid YAML"):
                apply_item("item-broken", owner_user_id="owner-1", skill_repo=skill_repo)

    def test_apply_to_library_rejects_non_string_skill_frontmatter_name(self):
        hub_resp = _make_hub_response("skill", "broken-skill", content="---\nname:\n  - broken\n---\nBody")
        skill_repo = SimpleNamespace(
            get_by_id=lambda _owner_user_id, _skill_id: None,
            list_for_owner=lambda _owner_user_id: [],
            upsert=lambda _skill: (_ for _ in ()).throw(AssertionError("must not save broken Skill")),
        )

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            from backend.hub.client import apply_item

            with pytest.raises(ValueError, match="Skill snapshot frontmatter must include name"):
                apply_item("item-broken", owner_user_id="owner-1", skill_repo=skill_repo)

    def test_apply_to_library_rejects_blank_skill_frontmatter_name(self):
        hub_resp = _make_hub_response("skill", "broken-skill", content="---\nname: '   '\n---\nBody")
        skill_repo = SimpleNamespace(
            get_by_id=lambda _owner_user_id, _skill_id: None,
            list_for_owner=lambda _owner_user_id: [],
            upsert=lambda _skill: (_ for _ in ()).throw(AssertionError("must not save broken Skill")),
        )

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            from backend.hub.client import apply_item

            with pytest.raises(ValueError, match="Skill snapshot frontmatter must include name"):
                apply_item("item-broken", owner_user_id="owner-1", skill_repo=skill_repo)

    def test_apply_to_library_does_not_read_skill_snapshot_meta(self):
        saved: list[Skill] = []
        packages: list[SkillPackage] = []
        hub_resp = _make_hub_response(
            "skill", "meta-free-skill", content="---\nname: Meta Free Skill\ndescription: Frontmatter wins\n---\nBody"
        )
        hub_resp["snapshot"]["meta"] = []
        skill_repo = SimpleNamespace(
            get_by_id=lambda _owner_user_id, _skill_id: None,
            list_for_owner=lambda _owner_user_id: [],
            upsert=lambda skill: saved.append(skill) or skill,
            create_package=lambda package: packages.append(package) or package,
            select_package=lambda _owner_user_id, _skill_id, _package_id: None,
        )

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            from backend.hub.client import apply_item

            apply_item("item-meta", owner_user_id="owner-1", skill_repo=skill_repo)

        assert saved[0].description == "Frontmatter wins"
        assert packages[0].skill_id == "meta-free-skill"

    def test_slug_path_shape_does_not_affect_library_id(self, monkeypatch):
        monkeypatch.setattr("backend.hub.client.generate_skill_id", lambda: "skill_evilSafe1")
        hub_resp = _make_hub_response("skill", "../../evil", content="---\nname: Evil\n---\n# Hello")
        saved: list[Skill] = []
        packages: list[SkillPackage] = []
        skill_repo = SimpleNamespace(
            get_by_id=lambda _owner_user_id, _skill_id: None,
            list_for_owner=lambda _owner_user_id: [],
            upsert=lambda skill: saved.append(skill) or skill,
            create_package=lambda package: packages.append(package) or package,
            select_package=lambda _owner_user_id, _skill_id, _package_id: None,
        )

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            from backend.hub.client import apply_item

            result = apply_item("item-evil", owner_user_id="owner-1", skill_repo=skill_repo)

        assert result["resource_id"] == "skill_evilSafe1"
        assert saved[0].id == "skill_evilSafe1"

    def test_apply_skill_saves_library_package_without_agent_config_write(self):
        import backend.hub.client as marketplace_client

        saved: list[AgentConfig] = []
        saved_skills: list[Skill] = []
        packages: list[SkillPackage] = []
        selected: list[tuple[str, str, str]] = []
        user_repo = SimpleNamespace(get_by_id=lambda user_id: SimpleNamespace(id=user_id, agent_config_id="cfg-1", owner_user_id="owner-1"))
        skill_repo = SimpleNamespace(
            get_by_id=lambda _owner_user_id, _skill_id: None,
            list_for_owner=lambda _owner_user_id: [],
            upsert=lambda skill: saved_skills.append(skill) or skill,
            create_package=lambda package: packages.append(package) or package,
            select_package=lambda owner_user_id, skill_id, package_id: selected.append((owner_user_id, skill_id, package_id)),
        )

        class _AgentConfigRepo:
            def get_agent_config(self, agent_config_id: str) -> AgentConfig | None:
                assert agent_config_id == "cfg-1"
                return _agent_config(
                    skills=[AgentSkill(skill_id="existing", package_id="existing-package", name="Existing", version="1.0.0")]
                )

            def save_agent_config(self, config: AgentConfig) -> None:
                saved.append(config)

        hub_resp = _make_hub_response(
            "skill",
            "fastapi",
            version="1.2.3",
            publisher="skillsmp",
            content="---\nname: FastAPI\ndescription: Build FastAPI APIs\n---\nAlways use APIRouter.",
        )
        hub_resp["snapshot"]["meta"]["desc"] = "Meta FastAPI description"
        hub_resp["snapshot"]["files"] = {"references/routing.md": "Prefer APIRouter."}

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            result = marketplace_client.apply_item(
                "skillsmp:fastapi",
                owner_user_id="owner-1",
                user_repo=user_repo,
                agent_config_repo=_AgentConfigRepo(),
                skill_repo=skill_repo,
            )

        assert result == {
            "resource_id": "fastapi",
            "package_id": packages[0].id,
            "type": "skill",
            "version": "1.2.3",
        }
        assert saved_skills[0].name == "FastAPI"
        assert saved_skills[0].description == "Build FastAPI APIs"
        assert packages[0].skill_md == "---\nname: FastAPI\ndescription: Build FastAPI APIs\n---\nAlways use APIRouter."
        assert packages[0].manifest["files"][0]["path"] == "references/routing.md"
        assert selected == [("owner-1", "fastapi", packages[0].id)]
        assert saved == []

    def test_saves_skill_to_library_without_agent_config_repo(self):
        import backend.hub.client as marketplace_client

        saved_configs: list[AgentConfig] = []
        saved_skills: list[Skill] = []
        packages: list[SkillPackage] = []
        user_repo = SimpleNamespace(get_by_id=lambda user_id: SimpleNamespace(id=user_id, agent_config_id="cfg-1", owner_user_id="owner-1"))
        skill_repo = SimpleNamespace(
            get_by_id=lambda _owner_user_id, _skill_id: None,
            list_for_owner=lambda _owner_user_id: [],
            upsert=lambda skill: saved_skills.append(skill) or skill,
            create_package=lambda package: packages.append(package) or package,
            select_package=lambda _owner_user_id, _skill_id, _package_id: None,
        )

        class _AgentConfigRepo:
            def get_agent_config(self, _agent_config_id: str) -> AgentConfig | None:
                return _agent_config(skills=[])

            def save_agent_config(self, config: AgentConfig) -> None:
                saved_configs.append(config)

        hub_resp = _make_hub_response(
            "skill",
            "fastapi",
            version="1.2.3",
            publisher="skillsmp",
            content="---\nname: FastAPI\ndescription: Build FastAPI APIs\n---\nAlways use APIRouter.",
        )

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            result = marketplace_client.apply_item(
                "skillsmp:fastapi",
                owner_user_id="owner-1",
                user_repo=user_repo,
                agent_config_repo=_AgentConfigRepo(),
                skill_repo=skill_repo,
            )

        assert saved_skills[0].id == "fastapi"
        assert saved_skills[0].name == "FastAPI"
        assert result == {
            "resource_id": "fastapi",
            "package_id": packages[0].id,
            "type": "skill",
            "version": "1.2.3",
        }
        assert saved_configs == []

    def test_apply_skill_uses_trimmed_frontmatter_name(self):
        import backend.hub.client as marketplace_client

        saved: list[AgentConfig] = []
        saved_skills: list[Skill] = []
        packages: list[SkillPackage] = []
        user_repo = SimpleNamespace(get_by_id=lambda user_id: SimpleNamespace(id=user_id, agent_config_id="cfg-1", owner_user_id="owner-1"))
        skill_repo = SimpleNamespace(
            get_by_id=lambda _owner_user_id, _skill_id: None,
            list_for_owner=lambda _owner_user_id: [],
            upsert=lambda skill: saved_skills.append(skill) or skill,
            create_package=lambda package: packages.append(package) or package,
            select_package=lambda _owner_user_id, _skill_id, _package_id: None,
        )

        class _AgentConfigRepo:
            def get_agent_config(self, _agent_config_id: str) -> AgentConfig | None:
                return _agent_config(skills=[])

            def save_agent_config(self, config: AgentConfig) -> None:
                saved.append(config)

        hub_resp = _make_hub_response(
            "skill",
            "fastapi",
            version="1.2.3",
            content='---\nname: " FastAPI "\n---\nAlways use APIRouter.',
        )

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            result = marketplace_client.apply_item(
                "skillsmp:fastapi",
                owner_user_id="owner-1",
                user_repo=user_repo,
                agent_config_repo=_AgentConfigRepo(),
                skill_repo=skill_repo,
            )

        assert result["resource_id"] == "fastapi"
        assert result["package_id"] == packages[0].id
        assert saved_skills[0].name == "FastAPI"
        assert saved == []


def test_apply_skill_to_agent_does_not_handwrite_binding_source() -> None:
    import inspect

    import backend.hub.client as marketplace_client

    source = inspect.getsource(marketplace_client.apply_item)

    assert 'source={\n                        "marketplace_item_id": item_id' not in source


def test_apply_skill_does_not_write_agent_config() -> None:
    import inspect

    import backend.hub.client as marketplace_client

    source = inspect.getsource(marketplace_client.apply_item)

    assert "AgentSkill(" not in source
    assert "save_agent_config" not in source
    assert "agent_user_id" not in inspect.signature(marketplace_client.apply_item).parameters


def test_apply_skill_to_agent_does_not_use_source_version_for_binding_version() -> None:
    import inspect

    import backend.hub.client as marketplace_client

    source = inspect.getsource(marketplace_client.apply_item)

    assert "version=source_version,\n                    source=" not in source


# ── Apply — agent ──


class TestApplyAgent:
    def test_apply_agent_item_type_is_not_supported(self):
        import backend.hub.client as marketplace_client

        hub_resp = _make_hub_response("agent", "old-agent-template", content="# Agent")

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            with pytest.raises(ValueError, match="Marketplace agent items are not supported"):
                marketplace_client.apply_item("item-agent")


class TestApplyUser:
    def test_member_type_applies_as_user_contract(self, monkeypatch):
        hub_resp = _make_hub_response("member", "agent-user")
        seen: dict[str, object] = {}

        monkeypatch.setattr(
            "backend.hub.client._snapshot_apply.apply_snapshot",
            lambda **kwargs: seen.update(kwargs) or "agent-user-1",
        )

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            from backend.hub.client import apply_item

            result = apply_item(
                "item-u1",
                owner_user_id="owner-1",
                user_repo=SimpleNamespace(),
                agent_config_repo=SimpleNamespace(),
                skill_repo=SimpleNamespace(),
            )

        assert result == {"user_id": "agent-user-1", "type": "user", "version": "1.0.0"}
        assert seen["user_repo"] is not None
        assert seen["agent_config_repo"] is not None
        assert seen["skill_repo"] is not None

    def test_member_type_apply_requires_repos(self):
        hub_resp = _make_hub_response("member", "agent-user")

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            from backend.hub.client import apply_item

            with pytest.raises(RuntimeError, match="user_repo and agent_config_repo are required"):
                apply_item("item-u1", owner_user_id="owner-1")


class TestApplyUnsupportedType:
    def test_apply_unsupported_item_type_raises_clear_error(self):
        hub_resp = _make_hub_response("env", "env-pack")

        with patch("backend.hub.client._hub_api", return_value=hub_resp):
            from backend.hub.client import apply_item

            with pytest.raises(ValueError, match="Unsupported item type: env"):
                apply_item("item-env")


# ── Apply idempotency ──


class TestApplyIdempotency:
    def test_apply_twice_upserts_same_skill_id(self, monkeypatch):
        generated_ids = iter(["skill_idem123", "skill_mustNotUse"])
        monkeypatch.setattr("backend.hub.client.generate_skill_id", lambda: next(generated_ids))
        saved: dict[str, Skill] = {}
        packages: list[SkillPackage] = []
        selected: list[tuple[str, str, str]] = []
        v1 = _make_hub_response("skill", "idem-skill", content="---\nname: Idem Skill\n---\nV1", version="1.0.0")
        v2 = _make_hub_response("skill", "idem-skill", content="---\nname: Idem Skill\n---\nV2", version="1.0.1")
        skill_repo = SimpleNamespace(
            get_by_id=lambda _owner_user_id, skill_id: saved.get(skill_id),
            list_for_owner=lambda _owner_user_id: list(saved.values()),
            upsert=lambda skill: saved.__setitem__(skill.id, skill) or skill,
            create_package=lambda package: packages.append(package) or package,
            select_package=lambda owner_user_id, skill_id, package_id: selected.append((owner_user_id, skill_id, package_id)),
        )

        from backend.hub.client import apply_item

        with patch("backend.hub.client._hub_api", return_value=v1):
            apply_item("item-idem", owner_user_id="owner-1", skill_repo=skill_repo)

        with patch("backend.hub.client._hub_api", return_value=v2):
            result = apply_item("item-idem", owner_user_id="owner-1", skill_repo=skill_repo)

        assert result["version"] == "1.0.1"
        assert result["package_id"] == packages[1].id
        assert list(saved) == ["skill_idem123"]
        assert saved["skill_idem123"].source["source_version"] == "1.0.1"
        assert packages[0].skill_md == "---\nname: Idem Skill\n---\nV1"
        assert packages[1].skill_md == "---\nname: Idem Skill\n---\nV2"
        assert selected[-1] == ("owner-1", "skill_idem123", packages[1].id)


def test_upgrade_returns_user_id_contract(monkeypatch):
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        "backend.hub.client._snapshot_apply.apply_snapshot",
        lambda **kwargs: seen.update(kwargs) or "agent-user-1",
    )

    with patch("backend.hub.client._hub_api", return_value=_make_hub_response("member", "agent-user", version="2.0.0")):
        from backend.hub.client import upgrade

        result = upgrade(
            user_id="agent-user-1",
            item_id="item-u2",
            owner_user_id="owner-1",
            user_repo=SimpleNamespace(),
            agent_config_repo=SimpleNamespace(),
            skill_repo=SimpleNamespace(),
        )

    assert result == {"user_id": "agent-user-1", "version": "2.0.0"}
    assert seen["user_repo"] is not None
    assert seen["agent_config_repo"] is not None
    assert seen["skill_repo"] is not None


def test_upgrade_passes_existing_user_id_to_snapshot_apply(monkeypatch):
    seen: dict[str, object] = {}

    def fake_apply_snapshot(**kwargs):
        seen.update(kwargs)
        return "agent-user-1"

    monkeypatch.setattr(
        "backend.hub.client._snapshot_apply.apply_snapshot",
        fake_apply_snapshot,
    )

    with patch("backend.hub.client._hub_api", return_value=_make_hub_response("member", "agent-user", version="2.0.0")):
        from backend.hub.client import upgrade

        upgrade(
            user_id="agent-user-1",
            item_id="item-u2",
            owner_user_id="owner-1",
            user_repo=SimpleNamespace(),
            agent_config_repo=SimpleNamespace(),
            skill_repo=SimpleNamespace(),
        )

    assert seen["existing_user_id"] == "agent-user-1"
    assert "existing_member_id" not in seen


def test_upgrade_requires_repos():
    with patch("backend.hub.client._hub_api", return_value=_make_hub_response("member", "agent-user", version="2.0.0")):
        from backend.hub.client import upgrade

        with pytest.raises(RuntimeError, match="user_repo and agent_config_repo are required"):
            upgrade(user_id="agent-user-1", item_id="item-u2", owner_user_id="owner-1")


def test_publish_uses_repo_material_when_member_dir_is_absent(tmp_path, monkeypatch):
    import backend.hub.client as marketplace_client

    saved: dict[str, AgentConfig] = {}
    captured: dict[str, Any] = {}

    user_repo = SimpleNamespace(get_by_id=lambda user_id: SimpleNamespace(id=user_id, agent_config_id="cfg-1", owner_user_id="owner-1"))

    class _AgentConfigRepo:
        def get_agent_config(self, agent_config_id: str):
            if agent_config_id != "cfg-1":
                return None
            return _agent_config(
                rules=[AgentRule(name="default", content="Rule content")],
                sub_agents=[AgentSubAgent(name="Scout", description="helper", tools=["search"], system_prompt="look around")],
                skills=[
                    AgentSkill(
                        skill_id="search",
                        package_id="search-package",
                        name="Search",
                        version="1.0.0",
                        source={"name": "Search", "desc": "Repo Search"},
                    )
                ],
            )

        def save_agent_config(self, config: AgentConfig) -> None:
            saved["config"] = config

    monkeypatch.setattr(
        marketplace_client,
        "_hub_api",
        lambda method, path, **kwargs: captured.update({"method": method, "path": path, "json": kwargs["json"]}) or {"item_id": "item-123"},
    )

    result = marketplace_client.publish(
        user_id="agent-user-1",
        type_=marketplace_client.HUB_AGENT_USER_ITEM_TYPE,
        bump_type="patch",
        release_notes="repo publish",
        tags=["repo"],
        visibility="private",
        publisher_user_id="owner-1",
        publisher_username="owner-name",
        user_repo=user_repo,
        agent_config_repo=_AgentConfigRepo(),
        skill_repo=SimpleNamespace(
            get_package=lambda _owner_user_id, package_id: SkillPackage(
                id=package_id,
                owner_user_id="owner-1",
                skill_id="search",
                version="1.0.0",
                hash="sha256:search",
                skill_md="---\nname: Search\n---\nskill content",
                source={"name": "Search", "desc": "Repo Search"},
                created_at=datetime(2026, 4, 25, tzinfo=UTC),
            )
        ),
    )

    assert result == {"item_id": "item-123"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/publish"
    payload = captured["json"]
    assert payload["name"] == "Repo Agent"
    assert payload["version"] == "0.1.1"
    assert payload["parent_item_id"] == "item-parent"
    assert payload["parent_version"] == "0.1.0"
    assert payload["snapshot"]["schema_version"] == "agent-snapshot/v1"
    assert payload["snapshot"]["agent"]["name"] == "Repo Agent"
    assert payload["snapshot"]["agent"]["meta"]["source"] == {"marketplace_item_id": "item-parent", "source_version": "0.1.0"}
    assert payload["snapshot"]["agent"]["rules"] == [{"id": None, "name": "default", "content": "Rule content", "enabled": True}]
    assert payload["snapshot"]["agent"]["skills"][0]["source"] == {"name": "Search", "desc": "Repo Search"}
    assert saved["config"].id == "cfg-1"
    assert saved["config"].owner_user_id == "owner-1"
    assert saved["config"].version == "0.1.1"
    assert saved["config"].status == "active"
    assert saved["config"].meta["source"]["marketplace_item_id"] == "item-123"
    assert saved["config"].meta["source"]["source_version"] == "0.1.1"


def test_publish_prefers_repo_lineage_even_when_stale_member_dir_exists(tmp_path, monkeypatch):
    import backend.hub.client as marketplace_client

    saved: dict[str, AgentConfig] = {}
    captured: dict[str, Any] = {}
    members_root = tmp_path / "members"
    member_dir = members_root / "agent-user-1"
    member_dir.mkdir(parents=True)
    stale_meta = {
        "status": "draft",
        "version": "9.9.9",
        "created_at": 1,
        "updated_at": 2,
        "source": {"marketplace_item_id": "stale-item", "source_version": "9.9.9"},
    }
    (member_dir / "meta.json").write_text(json.dumps(stale_meta, indent=2), encoding="utf-8")

    user_repo = SimpleNamespace(get_by_id=lambda user_id: SimpleNamespace(id=user_id, agent_config_id="cfg-1", owner_user_id="owner-1"))

    class _AgentConfigRepo:
        def get_agent_config(self, agent_config_id: str):
            if agent_config_id != "cfg-1":
                return None
            return _agent_config()

        def save_agent_config(self, config: AgentConfig) -> None:
            saved["config"] = config

    monkeypatch.setattr(
        marketplace_client,
        "_hub_api",
        lambda method, path, **kwargs: captured.update({"method": method, "path": path, "json": kwargs["json"]}) or {"item_id": "item-123"},
    )

    result = marketplace_client.publish(
        user_id="agent-user-1",
        type_=marketplace_client.HUB_AGENT_USER_ITEM_TYPE,
        bump_type="patch",
        release_notes="repo publish",
        tags=["repo"],
        visibility="private",
        publisher_user_id="owner-1",
        publisher_username="owner-name",
        user_repo=user_repo,
        agent_config_repo=_AgentConfigRepo(),
        skill_repo=SimpleNamespace(),
    )

    assert result == {"item_id": "item-123"}
    payload = captured["json"]
    assert payload["version"] == "0.1.1"
    assert payload["parent_item_id"] == "item-parent"
    assert payload["parent_version"] == "0.1.0"
    assert payload["snapshot"]["agent"]["meta"]["source"] == {"marketplace_item_id": "item-parent", "source_version": "0.1.0"}
    assert saved["config"].id == "cfg-1"
    assert saved["config"].owner_user_id == "owner-1"
    assert saved["config"].meta["source"]["marketplace_item_id"] == "item-123"
    assert saved["config"].meta["source"]["source_version"] == "0.1.1"
    assert json.loads((member_dir / "meta.json").read_text(encoding="utf-8")) == stale_meta


def test_publish_requires_repos():
    import backend.hub.client as marketplace_client

    with pytest.raises(RuntimeError, match="user_repo and agent_config_repo are required"):
        marketplace_client.publish(
            user_id="agent-user-1",
            type_=marketplace_client.HUB_AGENT_USER_ITEM_TYPE,
            bump_type="patch",
            release_notes="repo publish",
            tags=["repo"],
            visibility="private",
            publisher_user_id="owner-1",
            publisher_username="owner-name",
        )
