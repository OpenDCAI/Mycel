"""Core runtime configuration schema for Leon using Pydantic.

This module defines the runtime configuration structure with:
- Nested config groups (Memory, Tools, MCP, Skills)
- Runtime behavior parameters (temperature, max_tokens, context_limit, etc.)
- Field validators for paths, extensions

Model identity (model name, provider, API keys) lives in ModelsConfig (models_schema.py).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

# Default model used across the codebase — single source of truth
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

# ============================================================================
# Runtime Configuration (non-model behavior parameters)
# ============================================================================


class RuntimeConfig(BaseModel):
    """Runtime behavior configuration (non-model identity)."""

    temperature: float | None = Field(None, ge=0.0, le=2.0, description="Temperature")
    max_tokens: int | None = Field(None, gt=0, description="Max tokens")
    model_kwargs: dict[str, Any] = Field(default_factory=dict, description="Extra kwargs for init_chat_model")
    context_limit: int = Field(0, ge=0, description="Context window limit in tokens (0 = auto-detect from model)")
    enable_audit_log: bool = Field(True, description="Enable audit logging")
    allowed_extensions: list[str] | None = Field(None, description="Allowed extensions (None = all)")
    block_dangerous_commands: bool = Field(True, description="Block dangerous commands")
    block_network_commands: bool = Field(False, description="Block network commands")
    queue_mode: str = Field("steer", deprecated=True, description="Deprecated. Queue mode is now determined by message timing.")


# ============================================================================
# Memory Configuration
# ============================================================================


class PruningConfig(BaseModel):
    """Configuration for message pruning.

    Field names match SessionPruner constructor for direct passthrough.
    """

    enabled: bool = Field(True, description="Enable message pruning")
    soft_trim_chars: int = Field(3000, gt=0, description="Soft-trim tool results longer than this")
    hard_clear_threshold: int = Field(10000, gt=0, description="Hard-clear tool results longer than this")
    protect_recent: int = Field(3, gt=0, description="Keep last N tool messages untrimmed")
    trim_tool_results: bool = Field(True, description="Trim large tool results")


class CompactionConfig(BaseModel):
    """Configuration for context compaction.

    Field names match ContextCompactor constructor for direct passthrough.
    """

    enabled: bool = Field(True, description="Enable context compaction")
    reserve_tokens: int = Field(16384, gt=0, description="Reserve space for new messages")
    keep_recent_tokens: int = Field(20000, gt=0, description="Keep recent messages verbatim")
    min_messages: int = Field(20, gt=0, description="Minimum messages before compaction")


class MemoryConfig(BaseModel):
    """Memory management configuration."""

    pruning: PruningConfig = Field(default_factory=PruningConfig)
    compaction: CompactionConfig = Field(default_factory=CompactionConfig)


# ============================================================================
# Tools Configuration
# ============================================================================


class ReadFileConfig(BaseModel):
    """Configuration for read_file tool."""

    enabled: bool = True
    max_file_size: int = Field(10485760, gt=0, description="Max file size in bytes (10MB)")


class FileSystemToolsConfig(BaseModel):
    """Configuration for filesystem tools."""

    read_file: ReadFileConfig = Field(default_factory=ReadFileConfig)
    write_file: bool = True
    edit_file: bool = True
    list_dir: bool = True


class FileSystemConfig(BaseModel):
    """Configuration for filesystem middleware."""

    enabled: bool = True
    tools: FileSystemToolsConfig = Field(default_factory=FileSystemToolsConfig)


class GrepConfig(BaseModel):
    """Configuration for Grep tool."""

    enabled: bool = True
    max_file_size: int = Field(10485760, gt=0, description="Max file size in bytes (10MB)")


class SearchToolsConfig(BaseModel):
    """Configuration for search tools."""

    grep: GrepConfig = Field(default_factory=GrepConfig)
    glob: bool = True


class SearchConfig(BaseModel):
    """Configuration for search middleware."""

    enabled: bool = True
    tools: SearchToolsConfig = Field(default_factory=SearchToolsConfig)


class WebSearchConfig(BaseModel):
    """Configuration for web_search tool."""

    enabled: bool = True
    max_results: int = Field(5, gt=0, description="Max search results")
    tavily_api_key: str | None = Field(None, description="Tavily API key")
    exa_api_key: str | None = Field(None, description="Exa API key")
    firecrawl_api_key: str | None = Field(None, description="Firecrawl API key")


class FetchConfig(BaseModel):
    """Configuration for Fetch tool (AI extraction mode)."""

    enabled: bool = True
    jina_api_key: str | None = Field(None, description="Jina AI API key")


class WebToolsConfig(BaseModel):
    """Configuration for web tools."""

    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    fetch: FetchConfig = Field(default_factory=FetchConfig)


class WebConfig(BaseModel):
    """Configuration for web middleware."""

    enabled: bool = True
    timeout: int = Field(15, gt=0, description="Request timeout in seconds")
    tools: WebToolsConfig = Field(default_factory=WebToolsConfig)


class RunCommandConfig(BaseModel):
    """Configuration for run_command tool."""

    enabled: bool = True
    default_timeout: int = Field(120, gt=0, description="Default timeout in seconds")


class CommandToolsConfig(BaseModel):
    """Configuration for command tools."""

    run_command: RunCommandConfig = Field(default_factory=RunCommandConfig)
    command_status: bool = True


class CommandConfig(BaseModel):
    """Configuration for command middleware."""

    enabled: bool = True
    tools: CommandToolsConfig = Field(default_factory=CommandToolsConfig)


class SpillBufferConfig(BaseModel):
    """Configuration for SpillBuffer middleware."""

    enabled: bool = True
    default_threshold: int = Field(50_000, gt=0, description="Default spill threshold in bytes")
    thresholds: dict[str, int] = Field(
        default_factory=lambda: {
            "Grep": 20_000,
            "Glob": 20_000,
            "run_command": 50_000,
            "command_status": 50_000,
            "Fetch": 50_000,
        },
        description="Per-tool spill thresholds in bytes",
    )


class ToolsConfig(BaseModel):
    """Tools configuration."""

    filesystem: FileSystemConfig = Field(default_factory=FileSystemConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    command: CommandConfig = Field(default_factory=CommandConfig)
    spill_buffer: SpillBufferConfig = Field(default_factory=SpillBufferConfig)
    tool_modes: dict[str, str] = Field(
        default_factory=dict,
        description="Per-tool mode overrides: tool_name -> 'inline' | 'deferred'",
    )


# ============================================================================
# MCP Configuration
# ============================================================================


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    transport: str | None = Field(
        None,
        description="MCP transport type: stdio | streamable_http | sse | websocket",
    )
    command: str | None = Field(None, description="Command to run the MCP server")
    args: list[str] = Field(default_factory=list, description="Command arguments")
    env: dict[str, str] = Field(default_factory=dict, description="Environment variables")
    url: str | None = Field(None, description="URL for streamable HTTP transport")
    allowed_tools: list[str] | None = Field(None, description="Allowed tool names (None = all)")


class MCPConfig(BaseModel):
    """MCP (Model Context Protocol) configuration."""

    enabled: bool = True
    servers: dict[str, MCPServerConfig] = Field(default_factory=dict, description="MCP server configurations")


# ============================================================================
# Skills Configuration
# ============================================================================


class SkillsConfig(BaseModel):
    """Skills configuration."""

    enabled: bool = True
    paths: list[str] = Field(default_factory=lambda: ["./skills"], description="Skill search paths")
    skills: dict[str, bool] = Field(default_factory=dict, description="Skill enable/disable map")

    @field_validator("paths")
    @classmethod
    def validate_paths(cls, v: list[str]) -> list[str]:
        """Validate skill paths exist."""
        for path_str in v:
            path = Path(path_str).expanduser()
            if not path.exists():
                raise ValueError(f"Skill path does not exist: {path}")
        return v


# ============================================================================
# Main Settings
# ============================================================================


class LeonSettings(BaseModel):
    """Main Leon runtime configuration.

    Contains non-model runtime settings: memory, tools, mcp, skills, behavior params.
    Model identity (model name, provider, API keys) lives in ModelsConfig.

    Configuration priority (highest to lowest):
    1. CLI overrides
    2. Project config (.leon/runtime.json)
    3. User config (~/.leon/runtime.json)
    4. System defaults (config/defaults/runtime.json)
    """

    # Runtime behavior (replaces APIConfig model-identity fields)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig, description="Runtime behavior config")

    # Core configuration groups
    memory: MemoryConfig = Field(default_factory=MemoryConfig, description="Memory management")
    tools: ToolsConfig = Field(default_factory=ToolsConfig, description="Tools configuration")
    mcp: MCPConfig = Field(default_factory=MCPConfig, description="MCP configuration")
    skills: SkillsConfig = Field(default_factory=SkillsConfig, description="Skills configuration")

    # Agent configuration
    system_prompt: str | None = Field(None, description="Custom system prompt")
    workspace_root: str | None = Field(None, description="Workspace root directory")

    @field_validator("workspace_root")
    @classmethod
    def validate_workspace_root(cls, v: str | None) -> str | None:
        """Validate workspace_root exists."""
        if v is None:
            return v
        path = Path(v).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"Workspace root does not exist: {path}")
        if not path.is_dir():
            raise ValueError(f"Workspace root is not a directory: {path}")
        return str(path)
