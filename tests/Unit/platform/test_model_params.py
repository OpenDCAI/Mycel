"""Tests for model parameter normalization."""

from core.model_params import normalize_model_kwargs


def test_openai_gpt5_moves_max_tokens_to_max_completion_tokens() -> None:
    kwargs = {"model_provider": "openai", "max_tokens": 256, "base_url": "https://api.openai.com/v1"}
    out = normalize_model_kwargs("gpt-5.2", kwargs)
    assert "max_tokens" not in out
    assert out["max_completion_tokens"] == 256
    assert out["base_url"] == "https://api.openai.com/v1"


def test_openai_prefixed_gpt5_model_name_is_detected() -> None:
    kwargs = {"model_provider": "openai", "max_tokens": 128}
    out = normalize_model_kwargs("openai/gpt-5.1", kwargs)
    assert "max_tokens" not in out
    assert out["max_completion_tokens"] == 128


def test_existing_max_completion_tokens_wins_for_openai_gpt5() -> None:
    kwargs = {"model_provider": "openai", "max_tokens": 256, "max_completion_tokens": 64}
    out = normalize_model_kwargs("gpt-5.2", kwargs)
    assert "max_tokens" not in out
    assert out["max_completion_tokens"] == 64


def test_non_gpt5_openai_model_keeps_max_tokens() -> None:
    kwargs = {"model_provider": "openai", "max_tokens": 256}
    out = normalize_model_kwargs("gpt-4o", kwargs)
    assert out["max_tokens"] == 256
    assert "max_completion_tokens" not in out


def test_non_openai_provider_keeps_max_tokens() -> None:
    kwargs = {"model_provider": "anthropic", "max_tokens": 256}
    out = normalize_model_kwargs("gpt-5.2", kwargs)
    assert out["max_tokens"] == 256
    assert "max_completion_tokens" not in out


def test_openai_provider_matching_is_case_insensitive() -> None:
    kwargs = {"model_provider": "OpenAI", "max_tokens": 256}
    out = normalize_model_kwargs("gpt-5.2", kwargs)
    assert "max_tokens" not in out
    assert out["max_completion_tokens"] == 256
