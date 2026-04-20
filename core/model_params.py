"""Model parameter normalization for provider/model-specific request shapes."""

from __future__ import annotations

from typing import Any


def normalize_model_kwargs(model_name: str, model_kwargs: dict[str, Any]) -> dict[str, Any]:
    """Return model kwargs normalized for the target model/provider behavior."""
    kwargs = dict(model_kwargs)
    provider = str(kwargs.get("model_provider") or "").strip().lower()
    name = (model_name or "").strip().lower()

    # @@@openai-gpt5-token-param - OpenAI GPT-5 chat completions reject max_tokens and require max_completion_tokens.
    if provider == "openai" and _is_openai_gpt5(name):
        if "max_completion_tokens" not in kwargs and "max_tokens" in kwargs:
            kwargs["max_completion_tokens"] = kwargs["max_tokens"]
        kwargs.pop("max_tokens", None)

    return kwargs


def _is_openai_gpt5(model_name: str) -> bool:
    bare_name = model_name.split("/")[-1]
    return bare_name.startswith("gpt-5")
