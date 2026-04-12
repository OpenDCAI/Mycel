"""Pydantic models for panel API."""

from pydantic import BaseModel, Field

from backend.web.utils.versioning import BumpType

# ── Agents ──


class MemoryCompactionPayload(BaseModel):
    trigger_tokens: int | None = Field(default=None, gt=0)


class MemoryConfigPayload(BaseModel):
    compaction: MemoryCompactionPayload | None = None


class AgentConfigPayload(BaseModel):
    prompt: str | None = None
    rules: list[dict] | None = None
    tools: list[dict] | None = None
    mcps: list[dict] | None = None
    skills: list[dict] | None = None
    subAgents: list[dict] | None = None  # noqa: N815
    memory: MemoryConfigPayload | None = None


class CreateAgentRequest(BaseModel):
    name: str
    description: str = ""


class UpdateAgentRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


class PublishAgentRequest(BaseModel):
    bump_type: BumpType = "patch"
    notes: str = ""


# ── Library ──


class CreateResourceRequest(BaseModel):
    name: str
    desc: str = ""
    provider_name: str | None = None
    provider_type: str | None = None
    features: dict[str, bool] | None = None


class UpdateResourceRequest(BaseModel):
    name: str | None = None
    desc: str | None = None
    features: dict[str, bool] | None = None


class UpdateResourceContentRequest(BaseModel):
    content: str


# ── Profile ──


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    initials: str | None = None
    email: str | None = None
