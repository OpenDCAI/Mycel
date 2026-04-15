"""Tests for marketplace_client business logic (publish/download)."""

import importlib
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import backend.web.services.library_service as _lib_svc
from backend.web.utils.versioning import bump_semver

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
    import backend.web.services.marketplace_client as marketplace_client

    marketplace_client = importlib.reload(marketplace_client)

    assert marketplace_client._hub_client._trust_env is False


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


# ── Download — skill ──


class TestDownloadSkill:
    def test_writes_skill_md(self, tmp_path, monkeypatch):
        lib = tmp_path / "library"
        monkeypatch.setattr(_lib_svc, "LIBRARY_DIR", lib)
        hub_resp = _make_hub_response("skill", "my-skill", content="# My Skill\nDo stuff")

        with patch("backend.web.services.marketplace_client._hub_api", return_value=hub_resp):
            from backend.web.services.marketplace_client import download

            result = download("item-123")

        assert result["type"] == "skill"
        assert result["resource_id"] == "my-skill"
        skill_md = lib / "skills" / "my-skill" / "SKILL.md"
        assert skill_md.exists()
        assert skill_md.read_text(encoding="utf-8") == "# My Skill\nDo stuff"

    def test_meta_json_has_source_tracking(self, tmp_path, monkeypatch):
        lib = tmp_path / "library"
        monkeypatch.setattr(_lib_svc, "LIBRARY_DIR", lib)
        hub_resp = _make_hub_response("skill", "tracked-skill", version="2.1.0", publisher="alice")

        with patch("backend.web.services.marketplace_client._hub_api", return_value=hub_resp):
            from backend.web.services.marketplace_client import download

            download("item-456")

        meta = json.loads((lib / "skills" / "tracked-skill" / "meta.json").read_text(encoding="utf-8"))
        assert meta["source"]["marketplace_item_id"] == "item-456"
        assert meta["source"]["installed_version"] == "2.1.0"
        assert meta["source"]["publisher"] == "alice"

    def test_path_traversal_blocked(self, tmp_path, monkeypatch):
        lib = tmp_path / "library"
        monkeypatch.setattr(_lib_svc, "LIBRARY_DIR", lib)
        hub_resp = _make_hub_response("skill", "../../evil")

        with patch("backend.web.services.marketplace_client._hub_api", return_value=hub_resp):
            from backend.web.services.marketplace_client import download

            with pytest.raises(ValueError, match="Invalid slug"):
                download("item-evil")

        # Ensure no files written outside library
        assert not (tmp_path / "evil").exists()


# ── Download — agent ──


class TestDownloadAgent:
    def test_writes_agent_md(self, tmp_path, monkeypatch):
        lib = tmp_path / "library"
        monkeypatch.setattr(_lib_svc, "LIBRARY_DIR", lib)
        hub_resp = _make_hub_response("agent", "cool-agent", content="# Cool Agent")

        with patch("backend.web.services.marketplace_client._hub_api", return_value=hub_resp):
            from backend.web.services.marketplace_client import download

            result = download("item-a1")

        assert result["type"] == "agent"
        assert result["resource_id"] == "cool-agent"
        md_path = lib / "agents" / "cool-agent.md"
        assert md_path.exists()
        assert md_path.read_text(encoding="utf-8") == "# Cool Agent"

    def test_meta_json_written(self, tmp_path, monkeypatch):
        lib = tmp_path / "library"
        monkeypatch.setattr(_lib_svc, "LIBRARY_DIR", lib)
        hub_resp = _make_hub_response("agent", "meta-agent", version="3.0.0", publisher="bob")

        with patch("backend.web.services.marketplace_client._hub_api", return_value=hub_resp):
            from backend.web.services.marketplace_client import download

            download("item-a2")

        meta = json.loads((lib / "agents" / "meta-agent.json").read_text(encoding="utf-8"))
        assert meta["source"]["marketplace_item_id"] == "item-a2"
        assert meta["source"]["installed_version"] == "3.0.0"
        assert meta["source"]["publisher"] == "bob"


class TestDownloadUser:
    def test_member_type_installs_as_user_contract(self, monkeypatch):
        hub_resp = _make_hub_response("member", "agent-user")
        seen: dict[str, object] = {}

        monkeypatch.setattr(
            "backend.web.services.agent_user_service.install_from_snapshot",
            lambda **kwargs: seen.update(kwargs) or "agent-user-1",
        )

        with patch("backend.web.services.marketplace_client._hub_api", return_value=hub_resp):
            from backend.web.services.marketplace_client import download

            result = download(
                "item-u1",
                owner_user_id="owner-1",
                user_repo=SimpleNamespace(),
                agent_config_repo=SimpleNamespace(),
            )

        assert result == {"user_id": "agent-user-1", "type": "user", "version": "1.0.0"}
        assert seen["user_repo"] is not None
        assert seen["agent_config_repo"] is not None

    def test_member_type_download_requires_repos(self):
        hub_resp = _make_hub_response("member", "agent-user")

        with patch("backend.web.services.marketplace_client._hub_api", return_value=hub_resp):
            from backend.web.services.marketplace_client import download

            with pytest.raises(RuntimeError, match="user_repo and agent_config_repo are required"):
                download("item-u1", owner_user_id="owner-1")


# ── Download idempotency ──


class TestDownloadIdempotency:
    def test_download_twice_overwrites_cleanly(self, tmp_path, monkeypatch):
        lib = tmp_path / "library"
        monkeypatch.setattr(_lib_svc, "LIBRARY_DIR", lib)

        v1 = _make_hub_response("skill", "idem-skill", content="V1", version="1.0.0")
        v2 = _make_hub_response("skill", "idem-skill", content="V2", version="1.0.1")

        from backend.web.services.marketplace_client import download

        with patch("backend.web.services.marketplace_client._hub_api", return_value=v1):
            download("item-idem")

        with patch("backend.web.services.marketplace_client._hub_api", return_value=v2):
            result = download("item-idem")

        assert result["version"] == "1.0.1"
        content = (lib / "skills" / "idem-skill" / "SKILL.md").read_text(encoding="utf-8")
        assert content == "V2"
        meta = json.loads((lib / "skills" / "idem-skill" / "meta.json").read_text(encoding="utf-8"))
        assert meta["source"]["installed_version"] == "1.0.1"


def test_upgrade_returns_user_id_contract(monkeypatch):
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        "backend.web.services.agent_user_service.install_from_snapshot",
        lambda **kwargs: seen.update(kwargs) or "agent-user-1",
    )

    with patch(
        "backend.web.services.marketplace_client._hub_api", return_value=_make_hub_response("member", "agent-user", version="2.0.0")
    ):
        from backend.web.services.marketplace_client import upgrade

        result = upgrade(
            user_id="agent-user-1",
            item_id="item-u2",
            owner_user_id="owner-1",
            user_repo=SimpleNamespace(),
            agent_config_repo=SimpleNamespace(),
        )

    assert result == {"user_id": "agent-user-1", "version": "2.0.0"}
    assert seen["user_repo"] is not None
    assert seen["agent_config_repo"] is not None


def test_upgrade_passes_existing_user_id_to_snapshot_install(monkeypatch):
    seen: dict[str, object] = {}

    def fake_install_from_snapshot(**kwargs):
        seen.update(kwargs)
        return "agent-user-1"

    monkeypatch.setattr(
        "backend.web.services.agent_user_service.install_from_snapshot",
        fake_install_from_snapshot,
    )

    with patch(
        "backend.web.services.marketplace_client._hub_api", return_value=_make_hub_response("member", "agent-user", version="2.0.0")
    ):
        from backend.web.services.marketplace_client import upgrade

        upgrade(
            user_id="agent-user-1",
            item_id="item-u2",
            owner_user_id="owner-1",
            user_repo=SimpleNamespace(),
            agent_config_repo=SimpleNamespace(),
        )

    assert seen["existing_user_id"] == "agent-user-1"
    assert "existing_member_id" not in seen


def test_upgrade_requires_repos():
    with patch(
        "backend.web.services.marketplace_client._hub_api", return_value=_make_hub_response("member", "agent-user", version="2.0.0")
    ):
        from backend.web.services.marketplace_client import upgrade

        with pytest.raises(RuntimeError, match="user_repo and agent_config_repo are required"):
            upgrade(user_id="agent-user-1", item_id="item-u2", owner_user_id="owner-1")


def test_publish_uses_repo_bundle_when_member_dir_is_absent(tmp_path, monkeypatch):
    import backend.web.services.marketplace_client as marketplace_client

    saved: dict[str, object] = {}
    captured: dict[str, object] = {}

    user_repo = SimpleNamespace(get_by_id=lambda user_id: SimpleNamespace(id=user_id, agent_config_id="cfg-1"))

    class _AgentConfigRepo:
        def get_config(self, agent_config_id: str):
            if agent_config_id != "cfg-1":
                return None
            return {
                "id": "cfg-1",
                "agent_user_id": "agent-user-1",
                "name": "Repo Agent",
                "description": "from repo",
                "tools": ["search"],
                "system_prompt": "be helpful",
                "status": "draft",
                "version": "0.1.0",
                "created_at": 1,
                "updated_at": 2,
                "meta": {"source": {"marketplace_item_id": "item-parent", "installed_version": "0.1.0"}},
                "runtime": {"tools:search": {"enabled": True, "desc": "Search"}},
                "mcp": {"demo": {"transport": "stdio", "command": "demo"}},
            }

        def list_rules(self, agent_config_id: str):
            assert agent_config_id == "cfg-1"
            return [{"filename": "default.md", "content": "Rule content"}]

        def list_sub_agents(self, agent_config_id: str):
            assert agent_config_id == "cfg-1"
            return [{"name": "Scout", "description": "helper", "tools": ["search"], "system_prompt": "look around"}]

        def list_skills(self, agent_config_id: str):
            assert agent_config_id == "cfg-1"
            return [{"name": "Search", "content": "skill content", "meta_json": {"name": "Search", "desc": "Repo Search"}}]

        def save_config(self, agent_config_id: str, data: dict):
            saved["agent_config_id"] = agent_config_id
            saved["data"] = data

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
    )

    assert result == {"item_id": "item-123"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/publish"
    payload = captured["json"]
    assert payload["name"] == "Repo Agent"
    assert payload["version"] == "0.1.1"
    assert payload["parent_item_id"] == "item-parent"
    assert payload["parent_version"] == "0.1.0"
    assert payload["snapshot"]["agent_md"].startswith("---\n")
    assert payload["snapshot"]["meta"]["version"] == "0.1.0"
    assert payload["snapshot"]["meta"]["source"] == {"marketplace_item_id": "item-parent", "installed_version": "0.1.0"}
    assert payload["snapshot"]["rules"] == [{"name": "default", "content": "Rule content"}]
    assert payload["snapshot"]["skills"][0]["meta"] == {"name": "Search", "desc": "Repo Search"}
    assert saved["agent_config_id"] == "cfg-1"
    assert saved["data"]["version"] == "0.1.1"
    assert saved["data"]["status"] == "active"
    assert saved["data"]["meta"]["source"]["marketplace_item_id"] == "item-123"
    assert saved["data"]["meta"]["source"]["installed_version"] == "0.1.1"


def test_publish_prefers_repo_lineage_even_when_stale_member_dir_exists(tmp_path, monkeypatch):
    import backend.web.services.marketplace_client as marketplace_client

    saved: dict[str, object] = {}
    captured: dict[str, object] = {}
    members_root = tmp_path / "members"
    member_dir = members_root / "agent-user-1"
    member_dir.mkdir(parents=True)
    stale_meta = {
        "status": "draft",
        "version": "9.9.9",
        "created_at": 1,
        "updated_at": 2,
        "source": {"marketplace_item_id": "stale-item", "installed_version": "9.9.9"},
    }
    (member_dir / "meta.json").write_text(json.dumps(stale_meta, indent=2), encoding="utf-8")

    user_repo = SimpleNamespace(get_by_id=lambda user_id: SimpleNamespace(id=user_id, agent_config_id="cfg-1"))

    class _AgentConfigRepo:
        def get_config(self, agent_config_id: str):
            if agent_config_id != "cfg-1":
                return None
            return {
                "id": "cfg-1",
                "agent_user_id": "agent-user-1",
                "name": "Repo Agent",
                "description": "from repo",
                "tools": ["search"],
                "system_prompt": "be helpful",
                "status": "draft",
                "version": "0.1.0",
                "created_at": 1,
                "updated_at": 2,
                "meta": {"source": {"marketplace_item_id": "item-parent", "installed_version": "0.1.0"}},
                "runtime": {"tools:search": {"enabled": True, "desc": "Search"}},
                "mcp": {"demo": {"transport": "stdio", "command": "demo"}},
            }

        def list_rules(self, agent_config_id: str):
            assert agent_config_id == "cfg-1"
            return []

        def list_sub_agents(self, agent_config_id: str):
            assert agent_config_id == "cfg-1"
            return []

        def list_skills(self, agent_config_id: str):
            assert agent_config_id == "cfg-1"
            return []

        def save_config(self, agent_config_id: str, data: dict):
            saved["agent_config_id"] = agent_config_id
            saved["data"] = data

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
    )

    assert result == {"item_id": "item-123"}
    payload = captured["json"]
    assert payload["version"] == "0.1.1"
    assert payload["parent_item_id"] == "item-parent"
    assert payload["parent_version"] == "0.1.0"
    assert payload["snapshot"]["meta"]["source"] == {"marketplace_item_id": "item-parent", "installed_version": "0.1.0"}
    assert saved["agent_config_id"] == "cfg-1"
    assert saved["data"]["meta"]["source"]["marketplace_item_id"] == "item-123"
    assert saved["data"]["meta"]["source"]["installed_version"] == "0.1.1"
    assert json.loads((member_dir / "meta.json").read_text(encoding="utf-8")) == stale_meta


def test_publish_requires_repos():
    import backend.web.services.marketplace_client as marketplace_client

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
