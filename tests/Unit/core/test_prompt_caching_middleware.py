from types import SimpleNamespace

import pytest

from core.runtime.middleware import ModelRequest
from core.runtime.middleware.prompt_caching import PromptCachingMiddleware


def test_prompt_caching_warns_and_skips_unsupported_model(monkeypatch: pytest.MonkeyPatch):
    seen: list[str] = []

    monkeypatch.setattr("core.runtime.middleware.prompt_caching.warn", lambda msg, stacklevel=0: seen.append(str(msg)))

    middleware = PromptCachingMiddleware(unsupported_model_behavior="warn")
    request = ModelRequest(model=object(), messages=[SimpleNamespace()], system_message=None)

    assert middleware._should_apply_caching(request) is False
    assert len(seen) == 1
    assert "only supports Anthropic models" in seen[0]


def test_prompt_caching_applies_for_supported_anthropic_model(monkeypatch: pytest.MonkeyPatch):
    class _FakeAnthropicModel:
        pass

    monkeypatch.setattr("core.runtime.middleware.prompt_caching.ChatAnthropic", _FakeAnthropicModel)

    middleware = PromptCachingMiddleware(min_messages_to_cache=1, unsupported_model_behavior="raise")
    request = ModelRequest(model=_FakeAnthropicModel(), messages=[SimpleNamespace()], system_message=None)

    assert middleware._should_apply_caching(request) is True
