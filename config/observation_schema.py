"""Observation provider configuration schema.

Per-provider named fields, following sandbox/config.py pattern.
"""

from typing import Annotated

from pydantic import BaseModel, Field


class LangfuseConfig(BaseModel):
    """Langfuse provider config (dual key + host)."""

    secret_key: str | None = None
    public_key: str | None = None
    host: Annotated[str | None, Field(description="e.g. https://cloud.langfuse.com")] = None


class LangSmithConfig(BaseModel):
    """LangSmith provider config (api_key + project)."""

    api_key: str | None = None
    project: str | None = None
    endpoint: str | None = None


class ObservationConfig(BaseModel):
    """Observation configuration with per-provider named fields."""

    active: str | None = Field(None, description="'langfuse' | 'langsmith' | None (disabled)")
    langfuse: LangfuseConfig = Field(default_factory=lambda: LangfuseConfig())
    langsmith: LangSmithConfig = Field(default_factory=lambda: LangSmithConfig())
