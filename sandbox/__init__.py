"""Sandbox — infrastructure layer for execution environments.

Usage:
    from sandbox import create_sandbox, Sandbox, SandboxConfig

    config = SandboxConfig.load("agentbay")
    sbx = create_sandbox(config, db_path=db_path)

    FileSystemService(backend=sbx.fs())
    CommandService(executor=sbx.shell())
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sandbox.base import LocalSandbox, RemoteSandbox, Sandbox
from sandbox.config import SandboxConfig, resolve_sandbox_name
from sandbox.thread_context import get_current_thread_id, set_current_thread_id

logger = logging.getLogger(__name__)


def create_sandbox(
    config: SandboxConfig,
    workspace_root: str | None = None,
    db_path: Path | None = None,
) -> Sandbox:
    """Factory: create a Sandbox from config.

    Args:
        config: SandboxConfig (from SandboxConfig.load() or inline)
        workspace_root: Fallback working dir for LocalSandbox
        db_path: SQLite path for session tracking
    """
    p = config.provider

    if p == "local":
        return LocalSandbox(workspace_root=workspace_root or str(Path.cwd()), db_path=db_path)

    if p == "agentbay":
        from sandbox.providers.agentbay import AgentBayProvider

        ab = config.agentbay
        api_key = ab.api_key or os.getenv("AGENTBAY_API_KEY")
        if not api_key:
            raise ValueError("AgentBay sandbox requires AGENTBAY_API_KEY")
        logger.info("[AgentBaySandbox] Initialized (region=%s)", ab.region_id)
        return RemoteSandbox(
            provider=AgentBayProvider(
                api_key=api_key,
                region_id=ab.region_id,
                default_context_path=ab.context_path,
                image_id=ab.image_id,
                provider_name=config.name,
            ),
            config=config,
            default_cwd=ab.context_path,
            db_path=db_path,
            name=config.name,
            working_dir=ab.context_path,
            env_label="Remote Linux sandbox (Ubuntu)",
        )

    if p == "docker":
        from sandbox.providers.docker import DockerProvider

        dc = config.docker
        logger.info("[DockerSandbox] Initialized (image=%s)", dc.image)
        return RemoteSandbox(
            provider=DockerProvider(image=dc.image, mount_path=dc.mount_path, provider_name=config.name),
            config=config,
            default_cwd=dc.mount_path,
            db_path=db_path,
            name=config.name,
            working_dir=dc.mount_path,
            env_label="Local Docker sandbox (Ubuntu)",
        )

    if p == "e2b":
        from sandbox.providers.e2b import E2BProvider

        e = config.e2b
        api_key = e.api_key or os.getenv("E2B_API_KEY")
        if not api_key:
            raise ValueError("E2B sandbox requires E2B_API_KEY")
        logger.info("[E2BSandbox] Initialized (template=%s)", e.template)
        return RemoteSandbox(
            provider=E2BProvider(
                api_key=api_key,
                template=e.template,
                default_cwd=e.cwd,
                timeout=e.timeout,
                provider_name=config.name,
            ),
            config=config,
            default_cwd=e.cwd,
            db_path=db_path,
            name=config.name,
            working_dir=e.cwd,
            env_label="Remote Linux sandbox (E2B)",
        )

    if p == "daytona":
        from sandbox.providers.daytona import DaytonaProvider

        dt = config.daytona
        api_key = dt.api_key or os.getenv("DAYTONA_API_KEY")
        if not api_key:
            raise ValueError("Daytona sandbox requires DAYTONA_API_KEY")
        logger.info("[DaytonaSandbox] Initialized (target=%s)", dt.target)
        return RemoteSandbox(
            provider=DaytonaProvider(
                api_key=api_key,
                api_url=dt.api_url,
                target=dt.target,
                default_cwd=dt.cwd,
                provider_name=config.name,
            ),
            config=config,
            default_cwd=dt.cwd,
            db_path=db_path,
            name=config.name,
            working_dir=dt.cwd,
            env_label="Remote Linux sandbox (Daytona)",
        )

    raise ValueError(f"Unknown sandbox provider: {p}")


__all__ = [
    "Sandbox",
    "SandboxConfig",
    "create_sandbox",
    "resolve_sandbox_name",
    "set_current_thread_id",
    "get_current_thread_id",
    "RemoteSandbox",
    "LocalSandbox",
]
