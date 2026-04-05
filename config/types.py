"""Type definitions for agent configuration and bundles."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Agent configuration parsed from .md file."""

    name: str
    description: str = ""
    tools: list[str] = Field(default_factory=lambda: ["*"])
    system_prompt: str = ""
    model: str | None = None
    source_dir: Path | None = None


class McpServerConfig(BaseModel):
    """Single MCP server entry from .mcp.json."""

    transport: str | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    instructions: str | None = None
    allowed_tools: list[str] | None = None
    disabled: bool = False


class RuntimeResourceConfig(BaseModel):
    """Runtime config for a single tool/skill (enabled + description)."""

    enabled: bool = True
    desc: str = ""


class AgentBundle(BaseModel):
    """Complete agent bundle loaded from a directory."""

    agent: AgentConfig
    meta: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, RuntimeResourceConfig] = Field(default_factory=dict)
    rules: list[dict[str, str]] = Field(default_factory=list)
    agents: list[AgentConfig] = Field(default_factory=list)
    skills: list[dict[str, Any]] = Field(default_factory=list)
    mcp: dict[str, McpServerConfig] = Field(default_factory=dict)
