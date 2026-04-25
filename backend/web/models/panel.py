from pydantic import BaseModel, Field

from backend.hub.versioning import BumpType


class CompactConfigPayload(BaseModel):
    trigger_tokens: int | None = Field(default=None, gt=0)


class AgentConfigPayload(BaseModel):
    prompt: str | None = None
    rules: list[dict] | None = None
    tools: list[dict] | None = None
    mcpServers: list[dict] | None = None  # noqa: N815
    skills: list[dict] | None = None
    subAgents: list[dict] | None = None  # noqa: N815
    compact: CompactConfigPayload | None = None


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


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    initials: str | None = None
    email: str | None = None
