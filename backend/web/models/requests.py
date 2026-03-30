"""Pydantic request models for Leon web API."""

from typing import Literal

from pydantic import BaseModel, Field

from sandbox.config import MountSpec


class RecipeSnapshotRequest(BaseModel):
    id: str
    name: str
    provider_type: str
    desc: str | None = None
    features: dict[str, bool] = Field(default_factory=dict)


class CreateThreadRequest(BaseModel):
    member_id: str  # which agent template to create thread from
    sandbox: str = "local"
    recipe: RecipeSnapshotRequest | None = None
    lease_id: str | None = None
    cwd: str | None = None
    model: str | None = None
    agent: str | None = None
    bind_mounts: list[MountSpec] = Field(default_factory=list)


class ResolveMainThreadRequest(BaseModel):
    member_id: str


class SaveThreadLaunchConfigRequest(BaseModel):
    member_id: str
    create_mode: Literal["new", "existing"]
    provider_config: str
    recipe: RecipeSnapshotRequest | None = None
    lease_id: str | None = None
    model: str | None = None
    workspace: str | None = None


class RunRequest(BaseModel):
    message: str
    enable_trajectory: bool = False
    model: str | None = None
    attachments: list[str] = Field(default_factory=list)


class SendMessageRequest(BaseModel):
    message: str
    attachments: list[str] = Field(default_factory=list)
