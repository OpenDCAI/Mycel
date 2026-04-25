import inspect
import json
from pathlib import Path

from config.loader import AgentLoader
from config.schema import SkillsConfig
from core.runtime.agent import LeonAgent


def test_runtime_api_has_no_process_local_agent_config_source() -> None:
    blocked_arg = "agent_config" + "_dir"
    blocked_loader = "load_resolved_config" + "_from_dir"

    assert blocked_arg not in LeonAgent.__init__.__annotations__
    assert blocked_loader not in vars(AgentLoader)


def test_repo_backed_skill_registration_does_not_read_configured_skill_paths() -> None:
    source = inspect.getsource(LeonAgent._init_services)
    blocked_assignment = "skill_paths = " + "self.config.skills.paths"

    assert blocked_assignment not in source
    assert "has_repo_backed_agent_config" in source


def test_config_loading_does_not_create_skill_directories() -> None:
    loader_source = inspect.getsource(AgentLoader.load)
    skills_config_source = inspect.getsource(SkillsConfig)

    assert "mkdir" not in loader_source
    assert "path.exists()" not in skills_config_source


def test_runtime_defaults_do_not_read_host_skill_directory() -> None:
    runtime_defaults_path = Path(__file__).parents[3] / "config" / "defaults" / "runtime.json"
    runtime_defaults = json.loads(runtime_defaults_path.read_text())

    assert runtime_defaults["skills"]["paths"] == []
    assert AgentLoader().load().skills.paths == []
