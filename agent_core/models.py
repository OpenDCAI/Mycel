"""Model helpers.

The loop accepts any object with ``bind_tools`` + ``ainvoke`` (returning a
LangChain ``AIMessage``). Two conveniences here:

- ``build_chat_model`` — wraps LangChain's ``init_chat_model`` (Anthropic/OpenAI/…).
- ``OpenAIChatModel`` — a small native adapter over the ``openai`` SDK for any
  OpenAI-compatible endpoint; robust across LangChain version churn.

Both import their SDK lazily, so the core stays dependency-light.
"""

from __future__ import annotations

import json
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


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", "") if block.get("type") == "text" else "")
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return "" if content is None else str(content)


class OpenAIChatModel:
    """Minimal OpenAI-compatible chat model (``bind_tools`` + ``ainvoke``).

    Converts agent_core tool schemas + LangChain messages to the OpenAI wire
    format and parses responses back into a LangChain ``AIMessage`` (with
    ``tool_calls`` and ``usage_metadata``).
    """

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        _tools: list[dict] | None = None,
        **params: Any,
    ) -> None:
        self.model_name = model
        self._api_key = api_key
        self._base_url = self._normalize_base(base_url) if base_url else None
        self._tools = _tools
        self._params = params
        self._client: Any = None

    @staticmethod
    def _normalize_base(base: str) -> str:
        base = base.rstrip("/")
        return base if base.endswith("/v1") else base + "/v1"

    def _aclient(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI  # lazy import

            self._client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def bind_tools(self, tools: list) -> "OpenAIChatModel":
        clone = OpenAIChatModel(
            self.model_name,
            api_key=self._api_key,
            base_url=self._base_url,
            _tools=[self._to_openai_tool(t) for t in tools],
            **self._params,
        )
        clone._base_url = self._base_url
        clone._client = self._client  # reuse the async client
        return clone

    @staticmethod
    def _to_openai_tool(tool: Any) -> dict:
        if isinstance(tool, dict) and tool.get("type") == "function":
            return tool
        return {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
            },
        }

    @staticmethod
    def _to_openai_message(message: Any) -> dict:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

        if isinstance(message, SystemMessage):
            return {"role": "system", "content": _content_text(message.content)}
        if isinstance(message, ToolMessage):
            return {"role": "tool", "tool_call_id": message.tool_call_id, "content": _content_text(message.content)}
        if isinstance(message, AIMessage):
            out: dict = {"role": "assistant", "content": _content_text(message.content)}
            tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls:
                out["tool_calls"] = [
                    {
                        "id": tc.get("id") or f"call_{i}",
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": json.dumps(tc.get("args", {}))},
                    }
                    for i, tc in enumerate(tool_calls)
                ]
                if not out["content"]:
                    out["content"] = None
            return out
        return {"role": "user", "content": _content_text(getattr(message, "content", ""))}

    @staticmethod
    def _to_ai_message(response: Any) -> Any:
        from langchain_core.messages import AIMessage

        choice = response.choices[0].message
        tool_calls = []
        for tc in getattr(choice, "tool_calls", None) or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:  # noqa: BLE001
                args = {}
            tool_calls.append({"name": tc.function.name, "args": args, "id": tc.id, "type": "tool_call"})
        usage = getattr(response, "usage", None)
        usage_metadata = None
        if usage is not None:
            usage_metadata = {
                "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
            }
        return AIMessage(content=choice.content or "", tool_calls=tool_calls, usage_metadata=usage_metadata)

    async def ainvoke(self, messages: list) -> Any:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [self._to_openai_message(m) for m in messages],
            **self._params,
        }
        if self._tools:
            payload["tools"] = self._tools
        response = await self._aclient().chat.completions.create(**payload)
        return self._to_ai_message(response)
