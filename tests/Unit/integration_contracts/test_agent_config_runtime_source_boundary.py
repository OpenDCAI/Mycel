import inspect
import json
from pathlib import Path

from config.loader import AgentLoader
from config.models_loader import ModelsLoader
from config.observation_loader import ObservationLoader
from core.runtime.agent import LeonAgent


def test_runtime_api_has_no_process_local_agent_config_source() -> None:
    blocked_arg = "agent_config" + "_dir"
    blocked_loader = "load_resolved_config" + "_from_dir"

    assert blocked_arg not in LeonAgent.__init__.__annotations__
    assert blocked_loader not in vars(AgentLoader)


def test_runtime_skill_registration_reads_resolved_config_only() -> None:
    source = inspect.getsource(LeonAgent._init_services)

    assert "self.config.skills" not in source
    assert "skill_paths" not in source
    assert "resolved_skills" in source


def test_config_loading_does_not_create_skill_directories() -> None:
    loader_source = inspect.getsource(AgentLoader.load)

    assert "mkdir" not in loader_source


def test_runtime_config_loading_has_no_local_runtime_sources() -> None:
    loader_source = inspect.getsource(AgentLoader.load)

    assert "_load_user_config" not in loader_source
    assert "_load_project_config" not in loader_source
    assert "user_home_read_candidates" not in loader_source


def test_models_and_observation_loading_have_no_local_runtime_sources() -> None:
    models_source = inspect.getsource(ModelsLoader)
    observation_source = inspect.getsource(ObservationLoader)

    combined = f"{models_source}\n{observation_source}"
    assert "workspace_root" not in combined
    assert "_load_user" not in combined
    assert "_load_project" not in combined
    assert "user_home_read_candidates" not in combined


def test_runtime_defaults_do_not_define_skill_runtime_config() -> None:
    runtime_defaults_path = Path(__file__).parents[3] / "config" / "defaults" / "runtime.json"
    runtime_defaults = json.loads(runtime_defaults_path.read_text())

    assert "skills" not in runtime_defaults
    assert not hasattr(AgentLoader().load(), "skills")
