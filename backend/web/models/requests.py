"""Pydantic request models for Leon web API."""

from pydantic import BaseModel, Field

from sandbox.config import MountSpec


class CreateThreadRequest(BaseModel):
    member_id: str  # which agent template to create thread from
    sandbox: str = "local"
    cwd: str | None = None
    model: str | None = None
    agent: str | None = None
    bind_mounts: list[MountSpec] = Field(default_factory=list)
    workspace_id: str | None = None


class ResolveMainThreadRequest(BaseModel):
    member_id: str


class RunRequest(BaseModel):
    message: str
    enable_trajectory: bool = False
    model: str | None = None


class SendMessageRequest(BaseModel):
    message: str
