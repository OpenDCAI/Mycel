from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from config.skill_files import normalize_skill_file_map


def _require_enabled_bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError("enabled must be a boolean")
    return value


class AgentConfigSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Skill(AgentConfigSchemaModel):
    id: str
    owner_user_id: str
    name: str
    description: str = ""
    package_id: str | None = None
    source: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "owner_user_id", "name")
    @classmethod
    def _non_blank(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"skill.{info.field_name} must not be blank")
        return value


class SkillPackage(AgentConfigSchemaModel):
    id: str
    owner_user_id: str
    skill_id: str
    version: str
    hash: str
    manifest: dict[str, Any] = Field(default_factory=dict)
    skill_md: str
    files: dict[str, str] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @field_validator("id", "owner_user_id", "skill_id", "version", "hash", "skill_md")
    @classmethod
    def _non_blank(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"skill_package.{info.field_name} must not be blank")
        return value

    @field_validator("files", mode="before")
    @classmethod
    def _normalize_files(cls, value: Any) -> Any:
        return normalize_skill_file_map(value, context="Skill package files") if isinstance(value, dict) else value


class AgentSkill(AgentConfigSchemaModel):
    id: str | None = None
    skill_id: str | None = None
    package_id: str | None = None
    name: str
    description: str = ""
    version: str
    enabled: bool = True
    source: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _non_blank(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"agent_skill.{info.field_name} must not be blank")
        return value

    @field_validator("enabled", mode="before")
    @classmethod
    def _enabled_bool(cls, value: Any) -> bool:
        return _require_enabled_bool(value)


class ResolvedSkill(AgentConfigSchemaModel):
    name: str
    description: str = ""
    version: str
    content: str
    files: dict[str, str] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "version", "content")
    @classmethod
    def _non_blank(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"resolved_skill.{info.field_name} must not be blank")
        return value

    @field_validator("files", mode="before")
    @classmethod
    def _normalize_files(cls, value: Any) -> Any:
        return normalize_skill_file_map(value, context="Skill files") if isinstance(value, dict) else value


class AgentRule(AgentConfigSchemaModel):
    id: str | None = None
    name: str
    content: str
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _non_blank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("agent_rule.name must not be blank")
        return value

    @field_validator("enabled", mode="before")
    @classmethod
    def _enabled_bool(cls, value: Any) -> bool:
        return _require_enabled_bool(value)


class AgentSubAgent(AgentConfigSchemaModel):
    id: str | None = None
    name: str
    description: str = ""
    model: str | None = None
    tools: list[Any] = Field(default_factory=list)
    system_prompt: str = ""
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _non_blank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("agent_sub_agent.name must not be blank")
        return value

    @field_validator("enabled", mode="before")
    @classmethod
    def _enabled_bool(cls, value: Any) -> bool:
        return _require_enabled_bool(value)


class McpServerConfig(AgentConfigSchemaModel):
    id: str | None = None
    name: str
    transport: Literal["stdio", "streamable_http", "sse", "websocket"] | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    instructions: str | None = None
    allowed_tools: list[str] | None = None
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _non_blank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("mcp_server.name must not be blank")
        return value

    @field_validator("enabled", mode="before")
    @classmethod
    def _enabled_bool(cls, value: Any) -> bool:
        return _require_enabled_bool(value)


class AgentConfig(AgentConfigSchemaModel):
    id: str
    owner_user_id: str
    agent_user_id: str  # @@@aggregate-owner - DB column is not null; aggregate saves must persist it.
    name: str
    description: str = ""
    model: str | None = None
    tools: list[str] = Field(default_factory=lambda: ["*"])
    system_prompt: str = ""
    status: str = "draft"
    version: str
    runtime_settings: dict[str, Any] = Field(default_factory=dict)
    compact: dict[str, Any] = Field(default_factory=dict)
    skills: list[AgentSkill] = Field(default_factory=list)
    rules: list[AgentRule] = Field(default_factory=list)
    sub_agents: list[AgentSubAgent] = Field(default_factory=list)
    mcp_servers: list[McpServerConfig] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "owner_user_id", "agent_user_id", "name", "version")
    @classmethod
    def _non_blank_identity(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"agent_config.{info.field_name} must not be blank")
        return value


class ResolvedAgentConfig(AgentConfigSchemaModel):
    id: str
    name: str
    description: str = ""
    model: str | None = None
    tools: list[str] = Field(default_factory=lambda: ["*"])
    system_prompt: str = ""
    runtime_settings: dict[str, Any] = Field(default_factory=dict)
    compact: dict[str, Any] = Field(default_factory=dict)
    skills: list[ResolvedSkill] = Field(default_factory=list)
    rules: list[AgentRule] = Field(default_factory=list)
    sub_agents: list[AgentSubAgent] = Field(default_factory=list)
    mcp_servers: list[McpServerConfig] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class AgentSnapshot(AgentConfigSchemaModel):
    schema_version: Literal["agent-snapshot/v1"] = "agent-snapshot/v1"
    agent: ResolvedAgentConfig
