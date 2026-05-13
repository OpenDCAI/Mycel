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


def test_prompt_caching_raises_for_unsupported_model_when_configured(monkeypatch: pytest.MonkeyPatch):
    class _FakeAnthropicModel:
        pass

    monkeypatch.setattr("core.runtime.middleware.prompt_caching.ChatAnthropic", _FakeAnthropicModel)

    middleware = PromptCachingMiddleware(unsupported_model_behavior="raise")
    request = ModelRequest(model=object(), messages=[SimpleNamespace()], system_message=None)

    with pytest.raises(ValueError, match="only supports Anthropic models"):
        middleware._should_apply_caching(request)


def test_prompt_caching_applies_cache_control_to_string_system_message():
    middleware = PromptCachingMiddleware()
    request = ModelRequest(
        model=object(),
        messages=[],
        system_message=SimpleNamespace(content="system prompt"),
    )

    updated = middleware._apply_system_cache(request)

    assert updated.system_message.content == [{"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}]


def test_prompt_caching_applies_cache_control_to_first_system_block():
    middleware = PromptCachingMiddleware()
    request = ModelRequest(
        model=object(),
        messages=[],
        system_message=SimpleNamespace(
            content=[
                {"type": "text", "text": "system prompt"},
                {"type": "text", "text": "second block"},
            ]
        ),
    )

    updated = middleware._apply_system_cache(request)

    assert updated.system_message.content[0]["cache_control"] == {"type": "ephemeral"}
    assert updated.system_message.content[1] == {"type": "text", "text": "second block"}


def test_prompt_caching_leaves_request_unchanged_without_system_message():
    middleware = PromptCachingMiddleware()
    request = ModelRequest(model=object(), messages=[SimpleNamespace()], system_message=None)

    updated = middleware._apply_system_cache(request)

    assert updated is request


def test_prompt_caching_leaves_request_unchanged_for_empty_system_blocks():
    middleware = PromptCachingMiddleware()
    request = ModelRequest(
        model=object(),
        messages=[],
        system_message=SimpleNamespace(content=[]),
    )

    updated = middleware._apply_system_cache(request)

    assert updated is request
