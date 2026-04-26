from typing import Any

from .base import BaseMonitor


class ContextMonitor(BaseMonitor):
    def __init__(self, context_limit: int = 100000):
        self.context_limit = context_limit
        self.message_count = 0
        self.estimated_tokens = 0
        self._last_request_messages = 0

    def on_request(self, request: dict[str, Any]) -> None:
        messages = request.get("messages", [])
        if not isinstance(messages, list):
            messages = [messages]

        self.message_count = len(messages)
        self._last_request_messages = self.message_count

        self.estimated_tokens = self._estimate_tokens(messages)

    def on_response(self, request: dict[str, Any], response: dict[str, Any]) -> None:
        messages = response.get("messages", [])
        if isinstance(messages, list):
            new_messages = len(messages)
            self.message_count = self._last_request_messages + new_messages

            for msg in reversed(messages):
                usage = getattr(msg, "usage_metadata", None)
                if usage:
                    input_tokens = usage.get("input_tokens", 0) or 0
                    if input_tokens > 0:
                        self.estimated_tokens = input_tokens
                        return

    def _estimate_tokens(self, messages: list) -> int:
        total_chars = sum(self._extract_content_length(msg) for msg in messages)
        return total_chars // 2

    def _extract_content_length(self, msg) -> int:
        content = msg.content if hasattr(msg, "content") else msg.get("content", "") if isinstance(msg, dict) else ""

        if isinstance(content, str):
            return len(content)

        if isinstance(content, list):
            return sum(
                len(block.get("text", "")) if isinstance(block, dict) else len(block) for block in content if isinstance(block, (dict, str))
            )

        return 0

    def is_near_limit(self, threshold: float = 0.8) -> bool:
        return self.estimated_tokens >= self.context_limit * threshold

    def get_metrics(self) -> dict[str, Any]:
        usage_percent = (self.estimated_tokens / self.context_limit * 100) if self.context_limit > 0 else 0
        return {
            "message_count": self.message_count,
            "estimated_tokens": self.estimated_tokens,
            "context_limit": self.context_limit,
            "usage_percent": round(usage_percent, 1),
            "near_limit": self.is_near_limit(),
        }

    def reset(self) -> None:
        self.message_count = 0
        self.estimated_tokens = 0
