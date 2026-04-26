from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

from backend.sandboxes.local_workspace import local_workspace_root
from backend.sandboxes.paths import SANDBOXES_DIR
from sandbox.config import SandboxConfig
from sandbox.manager import SandboxManager
from sandbox.provider import ProviderCapability

logger = logging.getLogger(__name__)

_SANDBOX_INVENTORY_LOCK = threading.Lock()
_SANDBOX_INVENTORY: tuple[dict[str, Any], dict[str, Any]] | None = None


def _capability_to_dict(capability: ProviderCapability) -> dict[str, Any]:
    return {
        "can_pause": capability.can_pause,
        "can_resume": capability.can_resume,
        "can_destroy": capability.can_destroy,
        "supports_webhook": capability.supports_webhook,
        "supports_status_probe": capability.supports_status_probe,
        "eager_instance_binding": capability.eager_instance_binding,
        "inspect_visible": capability.inspect_visible,
        "runtime_kind": capability.runtime_kind,
        "mount": capability.mount.to_dict(),
    }


def _configured_api_key(name: str, configured: str | None, env_name: str) -> str | None:
    key = configured or os.getenv(env_name)
    if not key:
        logger.warning("[sandbox] %s configured but no API key; skipping", name)
        return None
    return key


def init_providers_and_managers() -> tuple[dict, dict]:
    global _SANDBOX_INVENTORY
    with _SANDBOX_INVENTORY_LOCK:
        if _SANDBOX_INVENTORY is None:
            # @@@sandbox-inventory-singleton - provider configs are process-lifetime state in local dev.
            # Build once and reuse so every API path does not rescan configs and re-instantiate failing providers.
            _SANDBOX_INVENTORY = _build_providers_and_managers()
        return _SANDBOX_INVENTORY


def _build_providers_and_managers(
    *,
    sandboxes_dir: Path | None = None,
    sandbox_manager_cls=SandboxManager,
    sandbox_config_cls=SandboxConfig,
    local_workspace_root_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    providers = _build_providers(
        sandboxes_dir=sandboxes_dir,
        sandbox_config_cls=sandbox_config_cls,
        local_workspace_root_path=local_workspace_root_path,
    )
    managers = {name: sandbox_manager_cls(provider=provider) for name, provider in providers.items()}
    return providers, managers


def _build_providers(
    *,
    sandboxes_dir: Path | None = None,
    sandbox_config_cls=SandboxConfig,
    local_workspace_root_path: Path | None = None,
) -> dict[str, Any]:
    from sandbox.providers.local import LocalSessionProvider

    config_dir = sandboxes_dir if sandboxes_dir is not None else SANDBOXES_DIR
    workspace_root = local_workspace_root_path or local_workspace_root()
    providers: dict[str, Any] = {
        "local": LocalSessionProvider(default_cwd=str(workspace_root)),
    }
    if config_dir is None or not config_dir.exists():
        return providers

    for config_file in config_dir.glob("*.json"):
        name = config_file.stem
        try:
            config = sandbox_config_cls.load(name, sandboxes_dir=config_dir)
            if config.provider == "agentbay":
                from sandbox.providers.agentbay import AgentBayProvider

                key = _configured_api_key(name, config.agentbay.api_key, "AGENTBAY_API_KEY")
                if not key:
                    continue
                providers[name] = AgentBayProvider(
                    api_key=key,
                    region_id=config.agentbay.region_id,
                    default_context_path=config.agentbay.context_path,
                    image_id=config.agentbay.image_id,
                    provider_name=name,
                    supports_pause=config.agentbay.supports_pause,
                    supports_resume=config.agentbay.supports_resume,
                )
            elif config.provider == "docker":
                from sandbox.providers.docker import DockerProvider

                providers[name] = DockerProvider(
                    image=config.docker.image,
                    mount_path=config.docker.mount_path,
                    default_cwd=config.docker.cwd,
                    bind_mounts=config.docker.bind_mounts,
                    provider_name=name,
                )
            elif config.provider == "e2b":
                from sandbox.providers.e2b import E2BProvider

                key = _configured_api_key(name, config.e2b.api_key, "E2B_API_KEY")
                if not key:
                    continue
                providers[name] = E2BProvider(
                    api_key=key,
                    template=config.e2b.template,
                    default_cwd=config.e2b.cwd,
                    timeout=config.e2b.timeout,
                    provider_name=name,
                )
            elif config.provider == "daytona":
                from sandbox.providers.daytona import DaytonaProvider

                key = _configured_api_key(name, config.daytona.api_key, "DAYTONA_API_KEY")
                if not key:
                    continue
                # @@@daytona-inventory-contract - current Daytona config/provider
                # shape is the narrow api_url/target/cwd/bind_mounts contract.
                # Do not reintroduce the older wider default_* / server_url /
                # workspace_provider argument set here unless the provider and
                # schema grow those fields again together.
                providers[name] = DaytonaProvider(
                    api_key=key,
                    api_url=config.daytona.api_url,
                    target=config.daytona.target,
                    default_cwd=config.daytona.cwd,
                    bind_mounts=config.daytona.bind_mounts,
                    provider_name=name,
                )
            else:
                logger.warning("[sandbox] unknown provider %s in %s", config.provider, config_file)
        except Exception as exc:
            logger.warning("[sandbox] failed to init provider %s: %s", name, exc)

    return providers


def available_sandbox_types(
    *,
    sandboxes_dir: Path | None = None,
    build_providers_fn=None,
    sandbox_config_cls=SandboxConfig,
) -> list[dict[str, Any]]:
    providers = (
        build_providers_fn()
        if build_providers_fn is not None
        else _build_providers(
            sandboxes_dir=sandboxes_dir,
            sandbox_config_cls=sandbox_config_cls,
        )
    )
    local_capability = providers["local"].get_capability()
    types = [
        {
            "name": "local",
            "provider": "local",
            "available": True,
            "capability": _capability_to_dict(local_capability),
        }
    ]
    config_dir = sandboxes_dir if sandboxes_dir is not None else SANDBOXES_DIR
    if config_dir is None or not config_dir.exists():
        return types
    for config_file in sorted(config_dir.glob("*.json")):
        name = config_file.stem
        try:
            config = sandbox_config_cls.load(name, sandboxes_dir=config_dir)
            provider_obj = providers.get(name)
            if provider_obj is None:
                types.append(
                    {
                        "name": name,
                        "provider": config.provider,
                        "available": False,
                        "reason": f"Provider {name} is configured but unavailable in the current process",
                    }
                )
                continue
            types.append(
                {
                    "name": name,
                    "provider": config.provider,
                    "available": True,
                    "capability": _capability_to_dict(provider_obj.get_capability()),
                }
            )
        except Exception as exc:
            types.append({"name": name, "available": False, "reason": str(exc)})
    return types


def load_provider_orphan_runtimes(managers: dict) -> list[dict[str, Any]]:
    runtimes: list[dict[str, Any]] = []
    for provider_name, manager in managers.items():
        provider = getattr(manager, "provider", None)
        list_provider_runtimes = getattr(provider, "list_provider_runtimes", None)
        if not callable(list_provider_runtimes):
            continue
        provider_slug = getattr(provider, "name", provider_name)

        seen_instance_ids = {
            str(row.get("current_instance_id") or "").strip()
            for row in manager.sandbox_runtime_store.list_by_provider(provider_slug)
            if str(row.get("current_instance_id") or "").strip()
        }
        raw_provider_runtimes = list_provider_runtimes()
        if not isinstance(raw_provider_runtimes, list):
            raise TypeError(f"{provider_slug}.list_provider_runtimes must return list")

        inspect_visible = manager.provider_capability.inspect_visible
        for provider_runtime in raw_provider_runtimes:
            instance_id = getattr(provider_runtime, "session_id", None)
            status = getattr(provider_runtime, "status", None) or "unknown"
            if not instance_id or status in {"deleted", "dead", "stopped"} or instance_id in seen_instance_ids:
                continue
            runtimes.append(
                {
                    "session_id": instance_id,
                    "thread_id": "(orphan)",
                    "provider": provider_slug,
                    "status": status,
                    "created_at": None,
                    "last_active": None,
                    "sandbox_runtime_id": None,
                    "instance_id": instance_id,
                    "chat_session_id": None,
                    "source": "provider_orphan",
                    "inspect_visible": inspect_visible,
                }
            )
    return runtimes


def list_provider_orphan_runtimes(*, init_providers_and_managers_fn=None) -> list[dict[str, Any]]:
    init_fn = init_providers_and_managers_fn or init_providers_and_managers
    _, managers = init_fn()
    return load_provider_orphan_runtimes(managers)
