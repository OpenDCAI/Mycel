"""Comprehensive tests for config.loader module."""

import json
import os
import sys
from pathlib import Path

import pytest

from config.loader import AgentLoader, ConfigLoader, load_bundle_from_repo, load_config
from config.schema import LeonSettings


class TestConfigLoader:
    """Tests for ConfigLoader."""

    def test_init(self, tmp_path):
        loader = ConfigLoader(workspace_root=str(tmp_path))
        assert loader.workspace_root == tmp_path

    def test_init_no_workspace(self):
        loader = ConfigLoader()
        assert loader.workspace_root is None

    def test_load_system_defaults_missing(self, tmp_path):
        loader = ConfigLoader()
        loader._system_defaults_dir = tmp_path / "nonexistent"

        result = loader._load_system_defaults()
        assert result == {}

    def test_load_user_config_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))

        loader = ConfigLoader()
        result = loader._load_user_config()
        assert result == {}

    def test_load_project_config_no_workspace(self):
        loader = ConfigLoader()
        result = loader._load_project_config()
        assert result == {}

    def test_load_project_config_missing(self, tmp_path):
        loader = ConfigLoader(workspace_root=str(tmp_path))
        result = loader._load_project_config()
        assert result == {}

    def test_deep_merge_simple(self):
        loader = ConfigLoader()

        dict1 = {"a": 1, "b": 2}
        dict2 = {"b": 3, "c": 4}

        result = loader._deep_merge(dict1, dict2)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_deep_merge_nested(self):
        loader = ConfigLoader()

        dict1 = {"api": {"model": "gpt-3", "temperature": 0.5}}
        dict2 = {"api": {"model": "gpt-4"}}

        result = loader._deep_merge(dict1, dict2)
        assert result["api"]["model"] == "gpt-4"
        assert result["api"]["temperature"] == 0.5

    def test_deep_merge_none_values(self):
        loader = ConfigLoader()

        dict1 = {"api": {"model": "gpt-4", "temperature": 0.5}}
        dict2 = {"api": {"temperature": None}}

        result = loader._deep_merge(dict1, dict2)
        # None values should not override
        assert result["api"]["temperature"] == 0.5

    def test_deep_merge_multiple(self):
        loader = ConfigLoader()

        dict1 = {"a": 1, "b": {"x": 1}}
        dict2 = {"b": {"y": 2}, "c": 3}
        dict3 = {"b": {"z": 3}, "d": 4}

        result = loader._deep_merge(dict1, dict2, dict3)
        assert result == {"a": 1, "b": {"x": 1, "y": 2, "z": 3}, "c": 3, "d": 4}

    def test_lookup_merge(self):
        loader = ConfigLoader()

        config1 = {"mcp": {"servers": {"server1": {}}}}
        config2 = {"mcp": {"servers": {"server2": {}}}}
        config3 = {"mcp": {"servers": {"server3": {}}}}

        # First found wins
        result = loader._lookup_merge("mcp", config1, config2, config3)
        assert "server1" in result["servers"]
        assert "server2" not in result["servers"]

    def test_lookup_merge_skip_none(self):
        loader = ConfigLoader()

        config1 = {"mcp": None}
        config2 = {"mcp": {"servers": {"server1": {}}}}

        result = loader._lookup_merge("mcp", config1, config2)
        assert "server1" in result["servers"]

    def test_lookup_merge_missing_key(self):
        loader = ConfigLoader()

        config1 = {"api": {}}
        config2 = {"tools": {}}

        result = loader._lookup_merge("mcp", config1, config2)
        assert result == {}

    def test_expand_env_vars_string(self):
        loader = ConfigLoader()

        os.environ["TEST_VAR"] = "test_value"
        result = loader._expand_env_vars("${TEST_VAR}")
        assert result == "test_value"

    def test_expand_env_vars_dict(self):
        loader = ConfigLoader()

        os.environ["API_KEY"] = "secret"
        obj = {"api": {"key": "${API_KEY}"}}
        result = loader._expand_env_vars(obj)
        assert result["api"]["key"] == "secret"

    def test_expand_env_vars_list(self):
        loader = ConfigLoader()

        os.environ["PATH1"] = "/path1"
        os.environ["PATH2"] = "/path2"
        obj = ["${PATH1}", "${PATH2}"]
        result = loader._expand_env_vars(obj)
        assert result == ["/path1", "/path2"]

    @pytest.mark.skipif(sys.platform == "win32", reason="HOME monkeypatch does not affect expanduser on Windows")
    def test_expand_env_vars_tilde(self, tmp_path, monkeypatch):
        loader = ConfigLoader()

        monkeypatch.setenv("HOME", str(tmp_path))
        result = loader._expand_env_vars("~/test")
        assert result == str(tmp_path / "test")

    def test_expand_env_vars_nested(self):
        loader = ConfigLoader()

        os.environ["BASE"] = "/base"
        obj = {
            "paths": ["${BASE}/path1", "${BASE}/path2"],
            "config": {"root": "${BASE}"},
        }
        result = loader._expand_env_vars(obj)
        assert result["paths"] == ["/base/path1", "/base/path2"]
        assert result["config"]["root"] == "/base"

    def test_discover_mcp_preserves_explicit_transport(self, tmp_path):
        path = tmp_path / ".mcp.json"
        path.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "wsdemo": {
                            "transport": "websocket",
                            "url": "ws://example.test/mcp",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        result = ConfigLoader._discover_mcp(tmp_path)

        assert result["wsdemo"].transport == "websocket"
        assert result["wsdemo"].url == "ws://example.test/mcp"


class TestLoadConfigFunction:
    """Tests for load_config convenience function."""

    def test_load_config_with_workspace(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        settings = load_config(workspace_root=str(project_dir))
        assert isinstance(settings, LeonSettings)


def test_project_agent_file_does_not_claim_bundle_source_dir(tmp_path: Path):
    agents_dir = tmp_path / ".leon" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "explore.md").write_text(
        "---\nname: explore\nmodel: project-model\n---\nproject prompt\n",
        encoding="utf-8",
    )

    agent = AgentLoader(workspace_root=tmp_path).load_all_agents()["explore"]

    assert agent.model == "project-model"
    assert agent.source_dir is None


def test_member_agent_retains_bundle_source_dir(tmp_path: Path, monkeypatch):
    home_root = tmp_path
    monkeypatch.setattr("config.loader.user_home_read_candidates", lambda *parts: (home_root.joinpath(*parts),))
    member_dir = home_root / "members" / "alice"
    member_dir.mkdir(parents=True)
    (member_dir / "agent.md").write_text(
        '---\nname: alice\ntools:\n  - "*"\n---\nmember prompt\n',
        encoding="utf-8",
    )

    agent = AgentLoader(workspace_root=tmp_path).load_all_agents()["alice"]

    assert agent.source_dir == member_dir.resolve()


def test_load_bundle_from_repo_uses_agent_config_id_root_key() -> None:
    seen: list[tuple[str, str]] = []

    class _Repo:
        def get_config(self, agent_config_id: str):
            seen.append(("config", agent_config_id))
            return {
                "id": agent_config_id,
                "name": "Toad",
                "description": "test config",
                "tools": ["search"],
                "system_prompt": "be helpful",
                "status": "active",
                "version": "1.0.0",
                "created_at": 1,
                "updated_at": 2,
                "meta": {"source": {"marketplace_item_id": "item-1", "installed_version": "1.0.0"}},
                "runtime": {"tools:search": {"enabled": True, "desc": "Search"}},
                "mcp": {},
            }

        def list_rules(self, agent_config_id: str):
            seen.append(("rules", agent_config_id))
            return [{"filename": "default.md", "content": "Be careful."}]

        def list_sub_agents(self, agent_config_id: str):
            seen.append(("sub_agents", agent_config_id))
            return [{"name": "Scout", "description": "helper", "tools": ["search"], "system_prompt": "look around"}]

        def list_skills(self, agent_config_id: str):
            seen.append(("skills", agent_config_id))
            return [{"name": "Search", "content": "search skill"}]

    bundle = load_bundle_from_repo(_Repo(), "cfg-1")

    assert bundle is not None
    assert bundle.agent.name == "Toad"
    assert bundle.meta["source"] == {"marketplace_item_id": "item-1", "installed_version": "1.0.0"}
    assert bundle.rules == [{"name": "default", "content": "Be careful."}]
    assert bundle.skills == [{"name": "Search", "content": "search skill"}]
    assert [agent.name for agent in bundle.agents] == ["Scout"]
    assert seen == [
        ("config", "cfg-1"),
        ("rules", "cfg-1"),
        ("sub_agents", "cfg-1"),
        ("skills", "cfg-1"),
    ]
