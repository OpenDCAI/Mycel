from collections.abc import Awaitable, Callable
from typing import Literal
from warnings import warn

from langchain_anthropic.chat_models import ChatAnthropic
from langchain_core.messages import SystemMessage

from core.runtime.middleware import (
    AgentMiddleware,
    ModelCallResult,
    ModelRequest,
    ModelResponse,
)


class PromptCachingMiddleware(AgentMiddleware):
    def __init__(
        self,
        type: Literal["ephemeral"] = "ephemeral",  # noqa: A002
        ttl: Literal["5m", "1h"] = "5m",
        min_messages_to_cache: int = 0,
        unsupported_model_behavior: Literal["ignore", "warn", "raise"] = "warn",
    ) -> None:
        self.type = type
        self.ttl = ttl
        self.min_messages_to_cache = min_messages_to_cache
        self.unsupported_model_behavior = unsupported_model_behavior

    def _apply_system_cache(self, request: ModelRequest) -> ModelRequest:
        sm = request.system_message
        if sm is None:
            return request
        content = sm.content
        if isinstance(content, str):
            new_content: list = [{"type": "text", "text": content, "cache_control": {"type": self.type}}]
        elif isinstance(content, list) and content:
            first = {**content[0], "cache_control": {"type": self.type}}
            new_content = [first, *content[1:]]
        else:
            return request
        return request.override(system_message=SystemMessage(content=new_content))

    def _should_apply_caching(self, request: ModelRequest) -> bool:
        if not isinstance(request.model, ChatAnthropic):
            msg = (
                "AnthropicPromptCachingMiddleware caching middleware only supports "
                f"Anthropic models, not instances of {type(request.model)}"
            )
            if self.unsupported_model_behavior == "raise":
                raise ValueError(msg)
            if self.unsupported_model_behavior == "warn":
                warn(msg, stacklevel=3)
            return False

        messages_count = len(request.messages)
        if request.system_message:
            messages_count += 1
        return messages_count >= self.min_messages_to_cache

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        if not self._should_apply_caching(request):
            return handler(request)
        return handler(self._apply_system_cache(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        if not self._should_apply_caching(request):
            return await handler(request)
        return await handler(self._apply_system_cache(request))


__all__ = ["PromptCachingMiddleware"]
