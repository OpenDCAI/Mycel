"""Type definitions for built-in runtime agent definitions."""

from pydantic import BaseModel, Field


class RuntimeAgentDefinition(BaseModel):
    """Built-in Agent configuration parsed from a bundled .md file."""

    name: str
    description: str = ""
    tools: list[str] = Field(default_factory=lambda: ["*"])
    system_prompt: str = ""
    model: str | None = None
