"""Models configuration schema for Leon.

Defines the unified models.json structure:
- active: current model selection
- providers: API credentials per provider
- mapping: virtual model (leon:*) → concrete model
- pool: enabled/custom model lists
- catalog: available model definitions (system-only)
- virtual_models: virtual model UI metadata (system-only)
"""

from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import BaseModel, Field

CredentialSource = Literal["platform", "user"]


class ProviderConfig(BaseModel):
    """Provider API credentials."""

    api_key: str | None = None
    base_url: str | None = None
    credential_source: CredentialSource | None = None


class ModelSpec(BaseModel):
    """Virtual model mapping entry."""

    model: str
    provider: str | None = None
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, gt=0)
    description: str | None = None
    based_on: str | None = None
    context_limit: int | None = Field(None, gt=0)


class ActiveModel(BaseModel):
    """Currently active model selection."""

    model: str = "claude-sonnet-4-5-20250929"
    provider: str | None = None
    based_on: str | None = None
    context_limit: int | None = Field(None, gt=0)


class CustomModelConfig(BaseModel):
    """Custom model metadata (based_on, context_limit)."""

    based_on: str | None = None
    context_limit: int | None = Field(None, gt=0)


class PoolConfig(BaseModel):
    """Model pool configuration."""

    enabled: list[str] = Field(default_factory=list)
    custom: list[str] = Field(default_factory=list)
    custom_config: dict[str, CustomModelConfig] = Field(default_factory=dict)


class CatalogEntry(BaseModel):
    """Model catalog entry (system-only)."""

    id: str
    name: str
    provider: str | None = None
    description: str | None = None


class VirtualModelEntry(BaseModel):
    """Virtual model UI metadata (system-only)."""

    id: str
    name: str
    icon: str | None = None
    description: str | None = None


class ModelsConfig(BaseModel):
    """Unified models configuration.

    Merge priority: system defaults → user (~/.leon/models.json) → project (.leon/models.json) → CLI
    """

    active: ActiveModel | None = None
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    mapping: dict[str, ModelSpec] = Field(default_factory=dict)
    pool: PoolConfig = Field(default_factory=PoolConfig)
    catalog: list[CatalogEntry] = Field(default_factory=list)
    virtual_models: list[VirtualModelEntry] = Field(default_factory=list)

    def resolve_model(self, name: str) -> tuple[str, dict[str, Any]]:
        """Resolve virtual model name to (actual_model, overrides).

        Args:
            name: Model name (can be leon:* virtual name)

        Returns:
            (actual_model_name, kwargs_dict)

        Raises:
            ValueError: If virtual model name not found in mapping
        """
        if not name.startswith("leon:"):
            if ":" in name:
                provider, model_name = name.split(":", 1)
                if provider in self.providers and model_name:
                    return model_name, {"model_provider": provider}
            overrides: dict[str, Any] = {}
            # From active model config
            if self.active:
                if self.active.based_on:
                    overrides["based_on"] = self.active.based_on
                if self.active.context_limit is not None:
                    overrides["context_limit"] = self.active.context_limit
            # From custom_config (higher priority for custom models)
            if name in self.pool.custom_config:
                cc = self.pool.custom_config[name]
                if cc.based_on:
                    overrides["based_on"] = cc.based_on
                if cc.context_limit is not None:
                    overrides["context_limit"] = cc.context_limit
            return name, overrides

        if name not in self.mapping:
            available = ", ".join(self.mapping.keys())
            raise ValueError(f"Unknown virtual model: {name}. Available: {available}")

        spec = self.mapping[name]
        kwargs: dict[str, Any] = {}
        if spec.provider:
            kwargs["model_provider"] = spec.provider
        if spec.temperature is not None:
            kwargs["temperature"] = spec.temperature
        if spec.max_tokens is not None:
            kwargs["max_tokens"] = spec.max_tokens
        # Inherit from custom_config of the resolved model (lower priority)
        resolved = spec.model
        if resolved in self.pool.custom_config:
            cc = self.pool.custom_config[resolved]
            if cc.based_on:
                kwargs["based_on"] = cc.based_on
            if cc.context_limit is not None:
                kwargs["context_limit"] = cc.context_limit
        # Mapping-level overrides (higher priority)
        if spec.based_on:
            kwargs["based_on"] = spec.based_on
        if spec.context_limit is not None:
            kwargs["context_limit"] = spec.context_limit
        return resolved, kwargs

    def get_provider(self, name: str) -> ProviderConfig | None:
        """Get provider credentials by name."""
        return self.providers.get(name)

    @staticmethod
    def _platform_api_key(provider_name: str | None) -> str | None:
        if provider_name == "anthropic":
            return os.getenv("ANTHROPIC_API_KEY")
        if provider_name == "openai":
            return os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")
        if provider_name == "openrouter":
            return os.getenv("OPENROUTER_API_KEY")
        if provider_name:
            return os.getenv(f"{provider_name.upper()}_API_KEY")
        return os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")

    @staticmethod
    def credential_source_for(provider: ProviderConfig | None) -> CredentialSource:
        if provider is None:
            return "platform"
        credential_source = getattr(provider, "credential_source", None)
        if credential_source:
            return credential_source
        return "user" if getattr(provider, "api_key", None) else "platform"

    def resolve_api_key(self, provider_name: str | None = None) -> str | None:
        """Resolve an API key for a provider without crossing credential-source boundaries."""
        if provider_name:
            provider = self.providers.get(provider_name)
            if self.credential_source_for(provider) == "user":
                return provider.api_key if provider else None
            return self._platform_api_key(provider_name)

        if self.active and self.active.provider:
            return self.resolve_api_key(self.active.provider)

        for name, provider in self.providers.items():
            if self.credential_source_for(provider) == "user" and provider.api_key:
                return provider.api_key
            if self.credential_source_for(provider) == "platform":
                key = self._platform_api_key(name)
                if key:
                    return key
        return self._platform_api_key(None)

    def get_active_provider(self) -> ProviderConfig | None:
        """Get provider credentials for the active model's provider."""
        if self.active and self.active.provider:
            return self.providers.get(self.active.provider)
        return None

    def get_api_key(self) -> str | None:
        """Get API key: active provider → any provider → env vars."""
        return self.resolve_api_key()

    def get_base_url(self) -> str | None:
        """Get base URL: active provider → env vars."""
        p = self.get_active_provider()
        if p and p.base_url:
            return p.base_url

        # From environment
        return os.getenv("ANTHROPIC_BASE_URL") or os.getenv("OPENAI_BASE_URL")

    def get_model_provider(self) -> str | None:
        """Get model provider: active.provider → auto-detect from env."""
        if self.active and self.active.provider:
            return self.active.provider

        # Auto-detect from environment
        if os.getenv("ANTHROPIC_API_KEY"):
            return "anthropic"
        if os.getenv("OPENAI_API_KEY"):
            return "openai"
        if os.getenv("OPENROUTER_API_KEY"):
            return "openai"
        return None
