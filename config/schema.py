"""Core runtime configuration schema for Mycel using Pydantic.

This module defines the runtime configuration structure with:
- Nested config groups (Memory, Tools)
- Runtime behavior parameters (temperature, max_tokens, context_limit, etc.)
- Field validators for paths, extensions

Model identity (model name, provider, API keys) lives in ModelsConfig (models_schema.py).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

# Default model used across the codebase — single source of truth
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

# ============================================================================
# Runtime Configuration (non-model behavior parameters)
# ============================================================================


class RuntimeSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeConfig(RuntimeSchemaModel):
    """Runtime behavior configuration (non-model identity)."""

    temperature: Annotated[float | None, Field(ge=0.0, le=2.0, description="Temperature")] = None
    max_tokens: Annotated[int | None, Field(gt=0, description="Max tokens")] = None
    model_kwargs: Annotated[dict[str, Any], Field(default_factory=dict, description="Extra kwargs for init_chat_model")] = Field(
        default_factory=dict
    )
    context_limit: Annotated[int, Field(ge=0, description="Context window limit in tokens (0 = auto-detect from model)")] = 0
    enable_audit_log: Annotated[StrictBool, Field(description="Enable audit logging")] = True
    allowed_extensions: Annotated[list[str] | None, Field(description="Allowed extensions (None = all)")] = None
    block_dangerous_commands: Annotated[StrictBool, Field(description="Block dangerous commands")] = True
    block_network_commands: Annotated[StrictBool, Field(description="Block network commands")] = False


# ============================================================================
# Memory Configuration
# ============================================================================


class PruningConfig(RuntimeSchemaModel):
    """Configuration for message pruning.

    Field names match SessionPruner constructor for direct passthrough.
    """

    enabled: Annotated[StrictBool, Field(description="Enable message pruning")] = True
    soft_trim_chars: Annotated[int, Field(gt=0, description="Soft-trim tool results longer than this")] = 3000
    hard_clear_threshold: Annotated[int, Field(gt=0, description="Hard-clear tool results longer than this")] = 10000
    protect_recent: Annotated[int, Field(gt=0, description="Keep last N tool messages untrimmed")] = 3
    trim_tool_results: Annotated[StrictBool, Field(description="Trim large tool results")] = True


class CompactionConfig(RuntimeSchemaModel):
    """Configuration for context compaction.

    Field names match ContextCompactor constructor for direct passthrough.
    """

    enabled: Annotated[StrictBool, Field(description="Enable context compaction")] = True
    reserve_tokens: Annotated[int, Field(gt=0, description="Reserve space for new messages")] = 16384
    keep_recent_tokens: Annotated[int, Field(gt=0, description="Keep recent messages verbatim")] = 20000
    min_messages: Annotated[int, Field(gt=0, description="Minimum messages before compaction")] = 20
    trigger_tokens: Annotated[int | None, Field(gt=0, description="Absolute token count that triggers compaction")] = None


class MemoryConfig(RuntimeSchemaModel):
    """Memory management configuration."""

    pruning: PruningConfig = Field(default_factory=lambda: PruningConfig())
    compaction: CompactionConfig = Field(default_factory=lambda: CompactionConfig())


# ============================================================================
# Tools Configuration
# ============================================================================


class FileSystemConfig(RuntimeSchemaModel):
    """Configuration for filesystem tools."""

    enabled: StrictBool = True
    max_file_size: Annotated[int, Field(gt=0, description="Max file size in bytes (10MB)")] = 10485760


class GrepConfig(RuntimeSchemaModel):
    """Configuration for Grep tool."""

    enabled: StrictBool = True
    max_file_size: Annotated[int, Field(gt=0, description="Max file size in bytes (10MB)")] = 10485760


class SearchToolsConfig(RuntimeSchemaModel):
    """Configuration for search tools."""

    grep: GrepConfig = Field(default_factory=lambda: GrepConfig())
    glob: StrictBool = True


class SearchConfig(RuntimeSchemaModel):
    """Configuration for search tools."""

    enabled: StrictBool = True
    tools: SearchToolsConfig = Field(default_factory=lambda: SearchToolsConfig())


class WebSearchConfig(RuntimeSchemaModel):
    """Configuration for the WebSearch tool."""

    enabled: StrictBool = True
    max_results: Annotated[int, Field(gt=0, description="Max search results")] = 5
    tavily_api_key: Annotated[str | None, Field(description="Tavily API key")] = None
    exa_api_key: Annotated[str | None, Field(description="Exa API key")] = None
    firecrawl_api_key: Annotated[str | None, Field(description="Firecrawl API key")] = None


class WebFetchConfig(RuntimeSchemaModel):
    """Configuration for the WebFetch tool."""

    enabled: StrictBool = True
    jina_api_key: Annotated[str | None, Field(description="Jina AI API key")] = None


class WebToolsConfig(RuntimeSchemaModel):
    """Configuration for web tools."""

    web_search: WebSearchConfig = Field(default_factory=lambda: WebSearchConfig())
    web_fetch: WebFetchConfig = Field(default_factory=lambda: WebFetchConfig())


class WebConfig(RuntimeSchemaModel):
    """Configuration for web tools."""

    enabled: StrictBool = True
    timeout: Annotated[int, Field(gt=0, description="Request timeout in seconds")] = 15
    tools: WebToolsConfig = Field(default_factory=lambda: WebToolsConfig())


class CommandConfig(RuntimeSchemaModel):
    """Configuration for command tools."""

    enabled: StrictBool = True


class SpillBufferConfig(RuntimeSchemaModel):
    """Configuration for SpillBuffer middleware."""

    enabled: StrictBool = True
    default_threshold: Annotated[int, Field(gt=0, description="Default spill threshold in bytes")] = 50_000
    thresholds: dict[str, int] = Field(
        default_factory=lambda: {
            "Grep": 20_000,
            "Glob": 20_000,
            "Bash": 50_000,
            "WebFetch": 50_000,
        },
        description="Per-tool spill thresholds in bytes",
    )


class ToolsConfig(RuntimeSchemaModel):
    """Tools configuration."""

    filesystem: FileSystemConfig = Field(default_factory=lambda: FileSystemConfig())
    search: SearchConfig = Field(default_factory=lambda: SearchConfig())
    web: WebConfig = Field(default_factory=lambda: WebConfig())
    command: CommandConfig = Field(default_factory=lambda: CommandConfig())
    spill_buffer: SpillBufferConfig = Field(default_factory=lambda: SpillBufferConfig())


# ============================================================================
# Main Settings
# ============================================================================


class LeonSettings(RuntimeSchemaModel):
    """Main Mycel runtime configuration.

    Contains non-model runtime settings: memory, tools, and behavior params.
    Model identity (model name, provider, API keys) lives in ModelsConfig.

    Configuration priority (highest to lowest):
    1. CLI overrides
    2. System defaults (config/defaults/runtime.json)
    """

    # Runtime behavior (replaces APIConfig model-identity fields)
    runtime: RuntimeConfig = Field(default_factory=lambda: RuntimeConfig(), description="Runtime behavior config")

    # Core configuration groups
    memory: MemoryConfig = Field(default_factory=lambda: MemoryConfig(), description="Memory management")
    tools: ToolsConfig = Field(default_factory=lambda: ToolsConfig(), description="Tools configuration")

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
