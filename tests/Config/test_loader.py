import json
import os
import sys
from os import PathLike
from pathlib import Path, PureWindowsPath

import pytest

from config.loader import AgentLoader, load_config
from config.schema import LeonSettings


class TestAgentLoader:
    def test_init(self, tmp_path):
        loader = AgentLoader(workspace_root=str(tmp_path))
        assert loader.workspace_root == tmp_path

    def test_init_no_workspace(self):
        loader = AgentLoader()
        assert loader.workspace_root is None

    def test_load_system_defaults_missing(self, tmp_path):
        loader = AgentLoader()
        loader._system_defaults_dir = tmp_path / "nonexistent"

        result = loader._load_system_defaults()
        assert result == {}

    def test_load_user_config_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))

        loader = AgentLoader()
        result = loader._load_user_config()
        assert result == {}

    def test_load_project_config_no_workspace(self):
        loader = AgentLoader()
        result = loader._load_project_config()
        assert result == {}

    def test_load_project_config_missing(self, tmp_path):
        loader = AgentLoader(workspace_root=str(tmp_path))
        result = loader._load_project_config()
        assert result == {}

    def test_load_project_config_rejects_invalid_runtime_json(self, tmp_path):
        project_dir = tmp_path / "project"
        (project_dir / ".leon").mkdir(parents=True)
        (project_dir / ".leon" / "runtime.json").write_text("{bad json", encoding="utf-8")

        loader = AgentLoader(workspace_root=str(project_dir))

        with pytest.raises(ValueError, match="Runtime config must be valid JSON"):
            loader._load_project_config()

    def test_load_project_config_rejects_non_object_runtime_json(self, tmp_path):
        project_dir = tmp_path / "project"
        (project_dir / ".leon").mkdir(parents=True)
        (project_dir / ".leon" / "runtime.json").write_text("[]", encoding="utf-8")

        loader = AgentLoader(workspace_root=str(project_dir))

        with pytest.raises(ValueError, match="Runtime config must be a JSON object"):
            loader._load_project_config()

    def test_deep_merge_simple(self):
        loader = AgentLoader()

        dict1 = {"a": 1, "b": 2}
        dict2 = {"b": 3, "c": 4}

        result = loader._deep_merge(dict1, dict2)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_deep_merge_nested(self):
        loader = AgentLoader()

        dict1 = {"api": {"model": "gpt-3", "temperature": 0.5}}
        dict2 = {"api": {"model": "gpt-4"}}

        result = loader._deep_merge(dict1, dict2)
        assert result["api"]["model"] == "gpt-4"
        assert result["api"]["temperature"] == 0.5

    def test_deep_merge_none_values(self):
        loader = AgentLoader()

        dict1 = {"api": {"model": "gpt-4", "temperature": 0.5}}
        dict2 = {"api": {"temperature": None}}

        result = loader._deep_merge(dict1, dict2)
        assert result["api"]["temperature"] == 0.5

    def test_deep_merge_multiple(self):
        loader = AgentLoader()

        dict1 = {"a": 1, "b": {"x": 1}}
        dict2 = {"b": {"y": 2}, "c": 3}
        dict3 = {"b": {"z": 3}, "d": 4}

        result = loader._deep_merge(dict1, dict2, dict3)
        assert result == {"a": 1, "b": {"x": 1, "y": 2, "z": 3}, "c": 3, "d": 4}

    def test_lookup_merge(self):
        loader = AgentLoader()

        config1 = {"mcp": {"servers": {"server1": {}}}}
        config2 = {"mcp": {"servers": {"server2": {}}}}
        config3 = {"mcp": {"servers": {"server3": {}}}}

        result = loader._lookup_merge("mcp", config1, config2, config3)
        assert "server1" in result["servers"]
        assert "server2" not in result["servers"]

    def test_lookup_merge_skip_none(self):
        loader = AgentLoader()

        config1 = {"mcp": None}
        config2 = {"mcp": {"servers": {"server1": {}}}}

        result = loader._lookup_merge("mcp", config1, config2)
        assert "server1" in result["servers"]

    def test_lookup_merge_missing_key(self):
        loader = AgentLoader()

        config1 = {"api": {}}
        config2 = {"tools": {}}

        result = loader._lookup_merge("mcp", config1, config2)
        assert result == {}

    def test_expand_env_vars_string(self):
        loader = AgentLoader()

        os.environ["TEST_VAR"] = "test_value"
        result = loader._expand_env_vars("${TEST_VAR}")
        assert result == "test_value"

    def test_expand_env_vars_dict(self):
        loader = AgentLoader()

        os.environ["API_KEY"] = "secret"
        obj = {"api": {"key": "${API_KEY}"}}
        result = loader._expand_env_vars(obj)
        assert result["api"]["key"] == "secret"

    def test_expand_env_vars_list(self):
        loader = AgentLoader()

        os.environ["PATH1"] = "/path1"
        os.environ["PATH2"] = "/path2"
        obj = ["${PATH1}", "${PATH2}"]
        result = loader._expand_env_vars(obj)
        assert result == ["/path1", "/path2"]

    @pytest.mark.skipif(sys.platform == "win32", reason="HOME monkeypatch does not affect expanduser on Windows")
    def test_expand_env_vars_tilde(self, tmp_path, monkeypatch):
        loader = AgentLoader()

        monkeypatch.setenv("HOME", str(tmp_path))
        result = loader._expand_env_vars("~/test")
        assert result == str(tmp_path / "test")

    def test_expand_env_vars_nested(self):
        loader = AgentLoader()

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

        result = AgentLoader._discover_mcp(tmp_path)

        assert result[0].name == "wsdemo"
        assert result[0].transport == "websocket"
        assert result[0].url == "ws://example.test/mcp"

    def test_discover_mcp_rejects_invalid_json(self, tmp_path):
        (tmp_path / ".mcp.json").write_text("{bad json", encoding="utf-8")

        with pytest.raises(ValueError, match="Local MCP config must be valid JSON"):
            AgentLoader._discover_mcp(tmp_path)

    def test_discover_mcp_rejects_non_object_servers(self, tmp_path):
        (tmp_path / ".mcp.json").write_text('{"mcpServers":[]}', encoding="utf-8")

        with pytest.raises(ValueError, match="Local MCP config mcpServers must be an object"):
            AgentLoader._discover_mcp(tmp_path)

    def test_discover_mcp_rejects_non_object_server_config(self, tmp_path):
        (tmp_path / ".mcp.json").write_text('{"mcpServers":{"demo":[]}}', encoding="utf-8")

        with pytest.raises(ValueError, match="Local MCP server config must be an object"):
            AgentLoader._discover_mcp(tmp_path)


class TestLoadConfigFunction:
    def test_load_config_with_workspace(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        settings = load_config(workspace_root=str(project_dir))
        assert isinstance(settings, LeonSettings)


def test_project_agent_file_stays_runtime_definition_only(tmp_path: Path):
    agents_dir = tmp_path / ".leon" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "explore.md").write_text(
        "---\nname: explore\nmodel: project-model\n---\nproject prompt\n",
        encoding="utf-8",
    )

    agent = AgentLoader(workspace_root=tmp_path).load_runtime_agents()["explore"]

    assert agent.model == "project-model"


def test_runtime_agent_discovery_excludes_member_dirs(tmp_path: Path, monkeypatch):
    home_root = tmp_path
    monkeypatch.setattr("config.loader.user_home_read_candidates", lambda *parts: (home_root.joinpath(*parts),))
    member_dir = home_root / "members" / "alice"
    member_dir.mkdir(parents=True)
    (member_dir / "agent.md").write_text(
        '---\nname: alice\ntools:\n  - "*"\n---\nmember prompt\n',
        encoding="utf-8",
    )

    assert "alice" not in AgentLoader(workspace_root=tmp_path).load_runtime_agents()


def test_load_resolved_config_from_dir_reads_local_agent_config(tmp_path: Path) -> None:
    agent_dir = tmp_path / "local-agent"
    (agent_dir / "rules").mkdir(parents=True)
    (agent_dir / "agents").mkdir()
    (agent_dir / "skills" / "Search").mkdir(parents=True)
    (agent_dir / "agent.md").write_text(
        "---\nname: Local Agent\ndescription: test config\ntools:\n  - search\n---\nbe helpful\n",
        encoding="utf-8",
    )
    (agent_dir / "runtime.json").write_text('{"tools:search":{"enabled":true,"desc":"Search"}}', encoding="utf-8")
    (agent_dir / "meta.json").write_text('{"source":{"marketplace_item_id":"item-1","source_version":"1.0.0"}}', encoding="utf-8")
    (agent_dir / "rules" / "default.md").write_text("Be careful.", encoding="utf-8")
    (agent_dir / "agents" / "Scout.md").write_text(
        "---\nname: Scout\ndescription: helper\ntools:\n  - search\n---\nlook around\n",
        encoding="utf-8",
    )
    (agent_dir / "skills" / "Search" / "SKILL.md").write_text(
        "---\nname: Search\ndescription: Repo Search\n---\nsearch skill",
        encoding="utf-8",
    )
    (agent_dir / "skills" / "Search" / "notes.md").write_text("extra", encoding="utf-8")
    (agent_dir / ".mcp.json").write_text(
        '{"mcpServers":{"demo":{"transport":"stdio","command":"demo","disabled":true}}}',
        encoding="utf-8",
    )

    resolved = AgentLoader().load_resolved_config_from_dir(agent_dir)

    assert resolved.name == "Local Agent"
    assert resolved.meta["source"] == {"marketplace_item_id": "item-1", "source_version": "1.0.0"}
    assert resolved.rules[0].name == "default"
    assert resolved.skills[0].name == "Search"
    assert resolved.skills[0].files == {"notes.md": "extra"}
    agent_names = {agent.name for agent in resolved.sub_agents}
    assert {"bash", "explore", "general", "plan", "Scout"}.issubset(agent_names)
    assert resolved.mcp_servers == []


def test_load_resolved_config_from_dir_stores_skill_adjacent_files_as_posix_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    agent_dir = tmp_path / "local-agent"
    skill_dir = agent_dir / "skills" / "Search"
    refs_dir = skill_dir / "references"
    refs_dir.mkdir(parents=True)
    (agent_dir / "agent.md").write_text("---\nname: Local Agent\n---\nbe helpful\n", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text("---\nname: Search\n---\nsearch skill", encoding="utf-8")
    (refs_dir / "query.md").write_text("extra", encoding="utf-8")
    original_relative_to = Path.relative_to

    def windows_relative_to(self: Path, *other: str | PathLike[str]) -> PureWindowsPath:
        relative_path = original_relative_to(self, *other)
        return PureWindowsPath(*relative_path.parts)

    monkeypatch.setattr(Path, "relative_to", windows_relative_to)

    resolved = AgentLoader().load_resolved_config_from_dir(agent_dir)

    assert resolved.skills[0].files == {"references/query.md": "extra"}


def test_load_resolved_config_from_dir_rejects_invalid_agent_md_yaml(tmp_path: Path) -> None:
    agent_dir = tmp_path / "local-agent"
    agent_dir.mkdir()
    (agent_dir / "agent.md").write_text("---\nname: [broken\n---\nbe helpful\n", encoding="utf-8")

    with pytest.raises(ValueError, match="agent.md frontmatter must be valid YAML"):
        AgentLoader().load_resolved_config_from_dir(agent_dir)


def test_load_resolved_config_from_dir_rejects_agent_md_without_name(tmp_path: Path) -> None:
    agent_dir = tmp_path / "local-agent"
    agent_dir.mkdir()
    (agent_dir / "agent.md").write_text("---\ndescription: missing name\n---\nbe helpful\n", encoding="utf-8")

    with pytest.raises(ValueError, match="agent.md frontmatter must include name"):
        AgentLoader().load_resolved_config_from_dir(agent_dir)


def test_load_resolved_config_from_dir_rejects_invalid_sub_agent_yaml(tmp_path: Path) -> None:
    agent_dir = tmp_path / "local-agent"
    (agent_dir / "agents").mkdir(parents=True)
    (agent_dir / "agent.md").write_text("---\nname: Local Agent\n---\nbe helpful\n", encoding="utf-8")
    (agent_dir / "agents" / "Scout.md").write_text("---\nname: [broken\n---\nlook around\n", encoding="utf-8")

    with pytest.raises(ValueError, match="agent.md frontmatter must be valid YAML"):
        AgentLoader().load_resolved_config_from_dir(agent_dir)


def test_load_resolved_config_from_dir_rejects_unreadable_rule_file(tmp_path: Path) -> None:
    agent_dir = tmp_path / "local-agent"
    (agent_dir / "rules").mkdir(parents=True)
    (agent_dir / "agent.md").write_text("---\nname: Local Agent\n---\nbe helpful\n", encoding="utf-8")
    (agent_dir / "rules" / "broken.md").write_bytes(b"\xff\xfe\xfa")

    with pytest.raises(RuntimeError, match="Local rule file could not be read"):
        AgentLoader().load_resolved_config_from_dir(agent_dir)


def test_load_resolved_config_from_dir_rejects_skill_without_frontmatter_name(tmp_path: Path) -> None:
    agent_dir = tmp_path / "local-agent"
    (agent_dir / "skills" / "Search").mkdir(parents=True)
    (agent_dir / "agent.md").write_text("---\nname: Local Agent\n---\nbe helpful\n", encoding="utf-8")
    (agent_dir / "skills" / "Search" / "SKILL.md").write_text("search skill", encoding="utf-8")

    with pytest.raises(ValueError, match="Local Skill content must include frontmatter name"):
        AgentLoader().load_resolved_config_from_dir(agent_dir)


def test_load_resolved_config_from_dir_rejects_skill_dir_without_skill_md(tmp_path: Path) -> None:
    agent_dir = tmp_path / "local-agent"
    (agent_dir / "skills" / "Search").mkdir(parents=True)
    (agent_dir / "agent.md").write_text("---\nname: Local Agent\n---\nbe helpful\n", encoding="utf-8")
    (agent_dir / "skills" / "Search" / "notes.md").write_text("notes", encoding="utf-8")

    with pytest.raises(ValueError, match="Local Skill directory must contain SKILL.md"):
        AgentLoader().load_resolved_config_from_dir(agent_dir)


def test_load_resolved_config_from_dir_rejects_invalid_skill_frontmatter_yaml(tmp_path: Path) -> None:
    agent_dir = tmp_path / "local-agent"
    (agent_dir / "skills" / "Search").mkdir(parents=True)
    (agent_dir / "agent.md").write_text("---\nname: Local Agent\n---\nbe helpful\n", encoding="utf-8")
    (agent_dir / "skills" / "Search" / "SKILL.md").write_text("---\nname: [broken\n---\nsearch skill", encoding="utf-8")

    with pytest.raises(ValueError, match="Local Skill frontmatter must be valid YAML"):
        AgentLoader().load_resolved_config_from_dir(agent_dir)


def test_load_resolved_config_from_dir_rejects_unreadable_skill_adjacent_file(tmp_path: Path) -> None:
    agent_dir = tmp_path / "local-agent"
    skill_dir = agent_dir / "skills" / "Search"
    skill_dir.mkdir(parents=True)
    (agent_dir / "agent.md").write_text("---\nname: Local Agent\n---\nbe helpful\n", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text("---\nname: Search\n---\nsearch skill", encoding="utf-8")
    (skill_dir / "broken.bin").write_bytes(b"\xff\xfe\xfa")

    with pytest.raises(RuntimeError, match="Local Skill adjacent file could not be read"):
        AgentLoader().load_resolved_config_from_dir(agent_dir)


def test_load_resolved_config_from_dir_rejects_invalid_runtime_json(tmp_path: Path) -> None:
    agent_dir = tmp_path / "local-agent"
    agent_dir.mkdir()
    (agent_dir / "agent.md").write_text("---\nname: Local Agent\n---\nbe helpful\n", encoding="utf-8")
    (agent_dir / "runtime.json").write_text("{bad json", encoding="utf-8")

    with pytest.raises(ValueError, match="Local runtime config must be valid JSON"):
        AgentLoader().load_resolved_config_from_dir(agent_dir)


def test_load_resolved_config_from_dir_rejects_non_object_runtime_json(tmp_path: Path) -> None:
    agent_dir = tmp_path / "local-agent"
    agent_dir.mkdir()
    (agent_dir / "agent.md").write_text("---\nname: Local Agent\n---\nbe helpful\n", encoding="utf-8")
    (agent_dir / "runtime.json").write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="Local runtime config must be a JSON object"):
        AgentLoader().load_resolved_config_from_dir(agent_dir)


def test_load_resolved_config_from_dir_rejects_invalid_meta_json(tmp_path: Path) -> None:
    agent_dir = tmp_path / "local-agent"
    agent_dir.mkdir()
    (agent_dir / "agent.md").write_text("---\nname: Local Agent\n---\nbe helpful\n", encoding="utf-8")
    (agent_dir / "meta.json").write_text("{bad json", encoding="utf-8")

    with pytest.raises(ValueError, match="Local Agent metadata must be valid JSON"):
        AgentLoader().load_resolved_config_from_dir(agent_dir)


def test_load_resolved_config_from_dir_rejects_non_object_meta_json(tmp_path: Path) -> None:
    agent_dir = tmp_path / "local-agent"
    agent_dir.mkdir()
    (agent_dir / "agent.md").write_text("---\nname: Local Agent\n---\nbe helpful\n", encoding="utf-8")
    (agent_dir / "meta.json").write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="Local Agent metadata must be a JSON object"):
        AgentLoader().load_resolved_config_from_dir(agent_dir)
