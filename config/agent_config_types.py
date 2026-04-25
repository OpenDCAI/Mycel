from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from config.skill_files import normalize_skill_file_map


class Skill(BaseModel):
    id: str
    owner_user_id: str
    name: str
    description: str = ""
    version: str = "0.1.0"
    content: str
    files: dict[str, str] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "owner_user_id", "name", "content")
    @classmethod
    def _non_blank(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"skill.{info.field_name} must not be blank")
        return value

    @field_validator("files", mode="before")
    @classmethod
    def _normalize_files(cls, value: Any) -> Any:
        return normalize_skill_file_map(value, context="Skill files") if isinstance(value, dict) else value


class AgentSkill(BaseModel):
    id: str | None = None
    skill_id: str | None = None
    name: str
    description: str = ""
    version: str = "0.1.0"
    content: str
    files: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    source: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "content")
    @classmethod
    def _non_blank(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"agent_skill.{info.field_name} must not be blank")
        return value

    @field_validator("files", mode="before")
    @classmethod
    def _normalize_files(cls, value: Any) -> Any:
        return normalize_skill_file_map(value, context="Skill files") if isinstance(value, dict) else value


class AgentRule(BaseModel):
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


class AgentSubAgent(BaseModel):
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


class McpServerConfig(BaseModel):
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


class AgentConfig(BaseModel):
    id: str
    owner_user_id: str
    agent_user_id: str  # @@@aggregate-owner - DB column is not null; aggregate saves must persist it.
    name: str
    description: str = ""
    model: str | None = None
    tools: list[str] = Field(default_factory=lambda: ["*"])
    system_prompt: str = ""
    status: str = "draft"
    version: str = "0.1.0"
    runtime_settings: dict[str, Any] = Field(default_factory=dict)
    compact: dict[str, Any] = Field(default_factory=dict)
    skills: list[AgentSkill] = Field(default_factory=list)
    rules: list[AgentRule] = Field(default_factory=list)
    sub_agents: list[AgentSubAgent] = Field(default_factory=list)
    mcp_servers: list[McpServerConfig] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "owner_user_id", "agent_user_id", "name")
    @classmethod
    def _non_blank_identity(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"agent_config.{info.field_name} must not be blank")
        return value


class ResolvedAgentConfig(BaseModel):
    id: str
    name: str
    description: str = ""
    model: str | None = None
    tools: list[str] = Field(default_factory=lambda: ["*"])
    system_prompt: str = ""
    runtime_settings: dict[str, Any] = Field(default_factory=dict)
    compact: dict[str, Any] = Field(default_factory=dict)
    skills: list[AgentSkill] = Field(default_factory=list)
    rules: list[AgentRule] = Field(default_factory=list)
    sub_agents: list[AgentSubAgent] = Field(default_factory=list)
    mcp_servers: list[McpServerConfig] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class AgentSnapshot(BaseModel):
    schema_version: Literal["agent-snapshot/v1"] = "agent-snapshot/v1"
    agent: ResolvedAgentConfig
