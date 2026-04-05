"""Comprehensive tests for config.loader module."""

import json
import os

import pytest

from config.loader import ConfigLoader, load_config
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


class TestLoadConfigFunction:
    """Tests for load_config convenience function."""

    def test_load_config_with_workspace(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        settings = load_config(workspace_root=str(project_dir))
        assert isinstance(settings, LeonSettings)
