"""Pydantic request models for Leon web API."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from sandbox.config import MountSpec


class CreateThreadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_user_id: str
    sandbox: str = "local"
    recipe_id: str | None = None
    existing_sandbox_id: str | None = None
    cwd: str | None = None
    model: str | None = None
    agent: str | None = None
    bind_mounts: list[MountSpec] = Field(default_factory=list)


class ResolveMainThreadRequest(BaseModel):
    agent_user_id: str


class SaveThreadLaunchConfigRequest(BaseModel):
    agent_user_id: str
    create_mode: Literal["new", "existing"]
    provider_config: str
    recipe_id: str | None = None
    existing_sandbox_id: str | None = None
    model: str | None = None
    workspace: str | None = None


class RunRequest(BaseModel):
    message: str
    enable_trajectory: bool = False
    model: str | None = None
    attachments: list[str] = Field(default_factory=list)


class SendMessageRequest(BaseModel):
    message: str
    enable_trajectory: bool = False
    attachments: list[str] = Field(default_factory=list)


class AskUserAnswerRequest(BaseModel):
    header: str | None = None
    question: str | None = None
    selected_options: list[str] = Field(default_factory=list)
    free_text: str | None = None


class ResolvePermissionRequest(BaseModel):
    decision: Literal["allow", "deny"]
    message: str | None = None
    answers: list[AskUserAnswerRequest] | None = None
    annotations: dict[str, Any] | None = None


class ThreadPermissionRuleRequest(BaseModel):
    behavior: Literal["allow", "deny", "ask"]
    tool_name: str
