import inspect
import json
from pathlib import Path

from backend.identity import profile as identity_profile
from backend.identity.avatar import files as avatar_files
from backend.identity.avatar import paths as avatar_paths
from backend.identity.avatar import urls as avatar_urls
from backend.threads import file_channel
from backend.web.routers import users as users_router
from config.loader import AgentLoader
from config.models_loader import ModelsLoader
from config.observation_loader import ObservationLoader
from core.runtime.agent import LeonAgent
from core.runtime.middleware.monitor import cost as cost_monitor
from sandbox import manager as sandbox_manager
from scripts import import_file_skills_to_library


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


def test_runtime_mcp_registration_reads_resolved_config_only() -> None:
    source = inspect.getsource(LeonAgent._get_mcp_server_configs) + inspect.getsource(LeonAgent._mcp_enabled)

    assert "self.config.mcp" not in source
    assert "resolved_config.mcp_servers" in source


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


def test_identity_profile_has_no_user_home_source() -> None:
    source = inspect.getsource(identity_profile)

    assert "user_home_path" not in source
    assert "preferred_existing_user_home_path" not in source
    assert "config.json" not in source


def test_cost_monitor_has_no_user_home_cache_source() -> None:
    source = inspect.getsource(cost_monitor)

    assert "config.user_paths" not in source
    assert "user_home_path" not in source
    assert "preferred_existing_user_home_path" not in source
    assert "pricing_cache.json" not in source


def test_file_channel_paths_have_no_user_home_source() -> None:
    source = f"{inspect.getsource(file_channel)}\n{inspect.getsource(sandbox_manager)}"

    assert "config.user_paths" not in source
    assert "user_home_path" not in source
    assert "file_channels" not in source


def test_avatar_storage_has_no_user_home_source() -> None:
    source = "\n".join(
        [
            inspect.getsource(avatar_paths),
            inspect.getsource(avatar_files),
            inspect.getsource(avatar_urls),
            inspect.getsource(users_router),
        ]
    )

    assert "config.user_paths" not in source
    assert "preferred_user_home_dir" not in source
    assert "AVATARS_DIR" not in source


def test_file_skill_import_has_no_default_host_library_path() -> None:
    source = inspect.getsource(import_file_skills_to_library)

    assert "backend.library.paths" not in source
    assert "LIBRARY_DIR" not in source
    assert "default=" not in source
