"""Optional helper to build a real chat model.

Kept out of the hot path: the loop accepts any object with ``bind_tools`` +
``ainvoke``. This helper just wraps LangChain's ``init_chat_model`` for
convenience and is imported lazily, so the core never hard-depends on a provider
SDK.
"""

from __future__ import annotations

from typing import Any


def build_chat_model(
    model_name: str,
    *,
    model_provider: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float | None = None,
    **kwargs: Any,
) -> Any:
    from langchain.chat_models import init_chat_model  # lazy import

    params: dict[str, Any] = dict(kwargs)
    if model_provider is not None:
        params["model_provider"] = model_provider
    if api_key is not None:
        params["api_key"] = api_key
    if base_url is not None:
        params["base_url"] = base_url
    if temperature is not None:
        params["temperature"] = temperature
    return init_chat_model(model_name, **params)
