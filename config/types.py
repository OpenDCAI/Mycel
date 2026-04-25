"""Type definitions for local runtime agent definitions."""

from pydantic import BaseModel, Field


class RuntimeAgentDefinition(BaseModel):
    """Agent configuration parsed from .md file."""

    name: str
    description: str = ""
    tools: list[str] = Field(default_factory=lambda: ["*"])
    system_prompt: str = ""
    model: str | None = None
