import logging
from typing import Any

import backend.sandboxes.user_reads as user_sandbox_reads
from backend.identity.avatar.urls import avatar_url
from backend.sandboxes import inventory as sandbox_inventory
from backend.sandboxes import provider_availability as _sandbox_provider_availability
from backend.sandboxes import provider_factory as _sandbox_provider_factory
from backend.sandboxes import recipe_catalog as _sandbox_recipe_catalog
from backend.sandboxes import thread_resources as _sandbox_thread_resources
from backend.sandboxes.local_workspace import local_workspace_root
from backend.sandboxes.paths import SANDBOXES_DIR
from backend.sandboxes.runtime import metrics as _sandbox_runtime_metrics
from backend.sandboxes.runtime import mutations as _sandbox_runtime_mutations
from backend.sandboxes.runtime import reads as _sandbox_runtime_reads
from backend.threads.projection import canonical_owner_threads
from backend.threads.virtual_threads import is_virtual_thread_id
from sandbox.config import SandboxConfig
from sandbox.manager import SandboxManager
from storage.runtime import build_sandbox_monitor_repo as make_sandbox_monitor_repo
from storage.runtime import build_storage_container

logger = logging.getLogger(__name__)


def list_default_recipes() -> list[dict[str, Any]]:
    return _sandbox_recipe_catalog.list_default_recipes()


def _list_user_runtime_rows(
    user_id: str,
    *,
    thread_repo: Any = None,
    user_repo: Any = None,
    include_runtime_session_id: bool = False,
) -> list[dict[str, Any]]:
    return user_sandbox_reads._list_user_runtime_rows(
        user_id,
        thread_repo=thread_repo,
        user_repo=user_repo,
        include_runtime_session_id=include_runtime_session_id,
        make_sandbox_monitor_repo_fn=make_sandbox_monitor_repo,
        canonical_owner_threads_fn=canonical_owner_threads,
        avatar_url_fn=avatar_url,
        is_virtual_thread_id_fn=is_virtual_thread_id,
    )


def list_user_sandboxes(
    user_id: str,
    *,
    thread_repo: Any = None,
    user_repo: Any = None,
) -> list[dict[str, Any]]:
    return user_sandbox_reads.list_user_sandboxes(
        user_id,
        thread_repo=thread_repo,
        user_repo=user_repo,
        make_sandbox_monitor_repo_fn=make_sandbox_monitor_repo,
        canonical_owner_threads_fn=canonical_owner_threads,
        avatar_url_fn=avatar_url,
        is_virtual_thread_id_fn=is_virtual_thread_id,
    )


def count_user_visible_sandboxes_by_provider(
    user_id: str,
    *,
    thread_repo: Any = None,
    supabase_client: Any | None = None,
) -> dict[str, int]:
    return user_sandbox_reads.count_user_visible_sandboxes_by_provider(
        user_id,
        thread_repo=thread_repo,
        supabase_client=supabase_client,
        make_sandbox_monitor_repo_fn=make_sandbox_monitor_repo,
        is_virtual_thread_id_fn=is_virtual_thread_id,
    )


def available_sandbox_types() -> list[dict[str, Any]]:
    return _sandbox_provider_availability.available_sandbox_types(
        sandboxes_dir=SANDBOXES_DIR,
        build_providers_fn=lambda: sandbox_inventory._build_providers(
            sandboxes_dir=SANDBOXES_DIR,
            sandbox_config_cls=SandboxConfig,
            local_workspace_root_path=local_workspace_root(),
        ),
        sandbox_config_cls=SandboxConfig,
    )


def init_providers_and_managers() -> tuple[dict, dict]:
    return sandbox_inventory.init_providers_and_managers()


def _build_providers_and_managers() -> tuple[dict[str, Any], dict[str, Any]]:
    return sandbox_inventory._build_providers_and_managers(
        sandboxes_dir=SANDBOXES_DIR,
        sandbox_manager_cls=SandboxManager,
        sandbox_config_cls=SandboxConfig,
        local_workspace_root_path=local_workspace_root(),
    )


def load_all_sandbox_runtimes(managers: dict) -> list[dict]:
    return _sandbox_runtime_reads.load_all_sandbox_runtimes(managers)


def load_provider_orphan_runtimes(managers: dict) -> list[dict]:
    return sandbox_inventory.load_provider_orphan_runtimes(managers)


def list_provider_orphan_runtimes() -> list[dict]:
    return sandbox_inventory.list_provider_orphan_runtimes(init_providers_and_managers_fn=init_providers_and_managers)


def find_runtime_and_manager(
    runtimes: list[dict],
    managers: dict,
    runtime_id: str,
    provider_name: str | None = None,
) -> tuple[dict | None, Any | None]:
    return _sandbox_runtime_reads.find_runtime_and_manager(
        runtimes,
        managers,
        runtime_id,
        provider_name=provider_name,
    )


def mutate_sandbox_runtime(
    *,
    runtime_id: str,
    action: str,
    provider_hint: str | None = None,
) -> dict[str, Any]:
    return _sandbox_runtime_mutations.mutate_sandbox_runtime(
        runtime_id=runtime_id,
        action=action,
        provider_hint=provider_hint,
        init_providers_and_managers_fn=init_providers_and_managers,
        load_all_sandbox_runtimes_fn=load_all_sandbox_runtimes,
        find_runtime_and_manager_fn=find_runtime_and_manager,
    )


def destroy_sandbox_runtime(*, sandbox_runtime_handle: str, provider_name: str, detach_thread_bindings: bool = False) -> dict[str, Any]:
    return _sandbox_runtime_mutations.destroy_sandbox_runtime(
        sandbox_runtime_handle=sandbox_runtime_handle,
        provider_name=provider_name,
        detach_thread_bindings=detach_thread_bindings,
        init_providers_and_managers_fn=init_providers_and_managers,
        build_storage_container_fn=build_storage_container,
    )


get_runtime_metrics = _sandbox_runtime_metrics.get_runtime_metrics


build_provider_from_config_name = _sandbox_provider_factory.build_provider_from_config_name


def destroy_thread_resources_sync(thread_id: str, sandbox_type: str, agent_pool: dict) -> bool:
    return _sandbox_thread_resources.destroy_thread_resources_sync(
        thread_id,
        sandbox_type,
        agent_pool,
        init_providers_and_managers_fn=init_providers_and_managers,
    )
