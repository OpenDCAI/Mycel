from pathlib import Path
from typing import Any

from backend.threads.event_bus import get_event_bus
from backend.threads.run.entrypoints import run_child_thread_live
from core.runtime.agent import create_leon_agent
from storage.runtime import build_storage_container


def create_agent_sync(
    sandbox_name: str,
    workspace_root: Path | None = None,
    model_name: str | None = None,
    agent: str | None = None,
    agent_config_id: str | None = None,
    agent_config_repo: Any = None,
    skill_repo: Any = None,
    thread_repo: Any = None,
    user_repo: Any = None,
    queue_manager: Any = None,
    chat_repos: dict | None = None,
    extra_allowed_paths: list[str] | None = None,
    web_app: Any = None,
    models_config_override: dict[str, Any] | None = None,
    memory_config_override: dict[str, Any] | None = None,
) -> Any:
    storage_container = build_storage_container()
    # @@@web-file-ops-repo - inject storage-backed repo so file_operations route to correct provider.
    from core.operations import FileOperationRecorder, set_recorder

    set_recorder(FileOperationRecorder(repo=storage_container.file_operation_repo()))
    return create_leon_agent(
        model_name=model_name,
        workspace_root=workspace_root or Path.cwd(),
        sandbox=sandbox_name if sandbox_name != "local" else None,
        storage_container=storage_container,
        permission_resolver_scope="thread",
        thread_repo=thread_repo,
        user_repo=user_repo,
        queue_manager=queue_manager,
        chat_repos=chat_repos,
        web_app=web_app,
        event_bus_factory=get_event_bus,
        child_thread_live_runner=run_child_thread_live,
        models_config_override=models_config_override,
        memory_config_override=memory_config_override,
        agent=agent,
        agent_config_id=agent_config_id,
        agent_config_repo=agent_config_repo,
        skill_repo=skill_repo,
        extra_allowed_paths=extra_allowed_paths,
    )
