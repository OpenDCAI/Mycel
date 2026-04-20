from typing import Any, cast

import pytest

from core.runtime.agent import LeonAgent


class _RuntimeModelProbe:
    def __init__(self) -> None:
        self.model_name = "gpt-5.4"
        self.api_key = "sk-test"
        self._model_http_client = None
        self._model_http_async_client = None

    def _build_model_kwargs(self) -> dict[str, Any]:
        return {
            "model_provider": "openai",
            "base_url": "http://provider.test/v1",
            "stream_usage": True,
        }

    def _build_openai_http_clients(self, provider: str | None) -> dict[str, Any]:
        return LeonAgent._build_openai_http_clients(cast(Any, self), provider)


def test_runtime_model_uses_persistent_openai_http_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_init_chat_model(model_name: str, **kwargs: Any) -> object:
        calls.append((model_name, kwargs))
        return object()

    monkeypatch.setattr("core.runtime.agent.init_chat_model", fake_init_chat_model)

    agent = _RuntimeModelProbe()

    LeonAgent._create_model(cast(Any, agent))

    assert len(calls) == 1
    model_name, kwargs = calls[0]
    assert model_name == "gpt-5.4"
    assert kwargs["api_key"] == "sk-test"
    assert kwargs["configurable_fields"] == ("model", "model_provider", "api_key", "base_url")
    assert kwargs["http_client"]._trust_env is False
    assert kwargs["http_async_client"]._trust_env is False
    assert agent._model_http_client is kwargs["http_client"]
    assert agent._model_http_async_client is kwargs["http_async_client"]


@pytest.mark.asyncio
async def test_runtime_model_client_cleanup_closes_both_clients() -> None:
    events: list[str] = []

    class _SyncClient:
        def close(self) -> None:
            events.append("sync")

    class _AsyncClient:
        async def aclose(self) -> None:
            events.append("async")

    agent = cast(Any, object.__new__(LeonAgent))
    agent._model_http_client = _SyncClient()
    agent._model_http_async_client = _AsyncClient()

    await LeonAgent._cleanup_model_clients(agent)

    assert events == ["async", "sync"]
    assert agent._model_http_client is None
    assert agent._model_http_async_client is None
