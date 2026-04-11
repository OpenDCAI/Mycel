from typing import Any, cast

import pytest

from config.models_schema import ModelsConfig, ModelSpec, ProviderConfig
from core.runtime.agent import LeonAgent


class _ExtractionAgentProbe:
    def __init__(self, config: ModelsConfig, *, api_key: str | None = None) -> None:
        self.api_key = api_key
        self.models_config = config
        self.verbose = False

    def _resolve_provider_name(self, _model_name: str, overrides: dict) -> str | None:
        return overrides.get("model_provider")

    def _normalize_base_url(self, base_url: str, provider: str | None) -> str:
        normalized = base_url.strip().rstrip("/")
        if normalized.endswith("/v1"):
            normalized = normalized[:-3]
        return normalized if provider == "anthropic" else f"{normalized}/v1"


def test_extraction_model_uses_resolved_provider_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict]] = []

    def fake_init_chat_model(model_name: str, **kwargs):
        calls.append((model_name, kwargs))
        return object()

    monkeypatch.setattr("core.runtime.agent.init_chat_model", fake_init_chat_model)

    config = ModelsConfig(
        providers={"anthropic": ProviderConfig(api_key="sk-mini", base_url="https://anthropic.example")},
        mapping={
            "leon:mini": ModelSpec(
                model="claude-haiku-4-5-20250929",
                provider="anthropic",
                temperature=None,
                max_tokens=None,
                context_limit=None,
            )
        },
    )
    agent = _ExtractionAgentProbe(config)

    result = LeonAgent._create_extraction_model(cast(Any, agent))

    assert result is not None
    assert calls == [
        (
            "claude-haiku-4-5-20250929",
            {
                "model_provider": "anthropic",
                "api_key": "sk-mini",
                "base_url": "https://anthropic.example",
            },
        )
    ]


def test_extraction_model_fails_loudly_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_init_chat_model(_model_name: str, **_kwargs):
        raise AssertionError("init_chat_model should not run without an api key")

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("core.runtime.agent.init_chat_model", fake_init_chat_model)

    config = ModelsConfig(
        providers={"anthropic": ProviderConfig(base_url="https://anthropic.example")},
        mapping={
            "leon:mini": ModelSpec(
                model="claude-haiku-4-5-20250929",
                provider="anthropic",
                temperature=None,
                max_tokens=None,
                context_limit=None,
            )
        },
    )
    agent = _ExtractionAgentProbe(config)

    with pytest.raises(RuntimeError, match="API key required for WebFetch extraction model"):
        LeonAgent._create_extraction_model(cast(Any, agent))
