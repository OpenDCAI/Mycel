"""Sandbox configuration.

Priority: --sandbox <name> > LEON_SANDBOX env > "local" (default)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class MountSpec(BaseModel):
    source: str
    target: str
    mode: Literal["mount", "copy"] = "mount"
    read_only: bool = False


class AgentBayConfig(BaseModel):
    api_key: str | None = None
    region_id: str = "ap-southeast-1"
    context_path: str = "/home/wuying"
    image_id: str | None = None
    supports_pause: bool | None = None
    supports_resume: bool | None = None


class DockerConfig(BaseModel):
    image: str = "python:3.12-slim"
    mount_path: str = "/workspace"
    docker_host: str | None = None  # e.g. "unix:///var/run/docker.sock" to bypass stuck Docker Desktop context
    cwd: str = "/workspace"
    bind_mounts: list[MountSpec] = Field(default_factory=list)


class E2BConfig(BaseModel):
    api_key: str | None = None
    template: str = "base"
    cwd: str = "/home/user"
    timeout: int = 300


class DaytonaConfig(BaseModel):
    api_key: str | None = None
    api_url: str = "https://app.daytona.io/api"
    target: str = "local"
    cwd: str = "/home/daytona"
    bind_mounts: list[MountSpec] = Field(default_factory=list)


class SandboxConfig(BaseModel):
    provider: str = "local"
    # @@@ config-name-propagation - carries the config file stem (e.g. "daytona_selfhost") through the pipeline
    name: str = "local"
    console_url: str | None = None
    agentbay: AgentBayConfig = Field(default_factory=AgentBayConfig)
    docker: DockerConfig = Field(default_factory=DockerConfig)
    e2b: E2BConfig = Field(default_factory=E2BConfig)
    daytona: DaytonaConfig = Field(default_factory=DaytonaConfig)
    on_exit: str = "pause"
    init_commands: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)

    @classmethod
    def load(cls, name: str) -> SandboxConfig:
        if name == "local":
            return cls()

        path = Path.home() / ".leon" / "sandboxes" / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Sandbox config not found: {path}")

        data = json.loads(path.read_text())
        config = cls(**data)
        config.name = name
        return config

    def save(self, name: str) -> Path:
        path = Path.home() / ".leon" / "sandboxes" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {"provider": self.provider, "on_exit": self.on_exit}
        if self.console_url:
            data["console_url"] = self.console_url
        if self.init_commands:
            data["init_commands"] = self.init_commands
        if self.allowed_paths:
            data["allowed_paths"] = self.allowed_paths
        if self.provider in ("agentbay", "docker", "e2b", "daytona"):
            data[self.provider] = getattr(self, self.provider).model_dump()

        path.write_text(json.dumps(data, indent=2))
        return path


def resolve_sandbox_name(cli_arg: str | None) -> str:
    if cli_arg:
        return cli_arg
    return os.getenv("LEON_SANDBOX", "local")
