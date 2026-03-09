"""上下文大小监控"""

from typing import Any

from .base import BaseMonitor


class ContextMonitor(BaseMonitor):
    """追踪上下文大小

    统计 messages 数量和估算 token 数。
    为后续的上下文压缩功能提供数据支持。
    """

    def __init__(self, context_limit: int = 100000):
        self.context_limit = context_limit
        self.message_count = 0
        self.estimated_tokens = 0
        self._last_request_messages = 0

    def on_request(self, request: dict[str, Any]) -> None:
        """请求前：统计当前上下文大小"""
        messages = request.get("messages", [])
        if not isinstance(messages, list):
            messages = [messages]

        self.message_count = len(messages)
        self._last_request_messages = self.message_count

        # 估算 token 数（粗略：每条消息平均 100 tokens）
        # 后续可以用 tiktoken 精确计算
        self.estimated_tokens = self._estimate_tokens(messages)

    def on_response(self, request: dict[str, Any], response: dict[str, Any]) -> None:
        """响应后：用 API 返回的真实 input_tokens 更新上下文大小"""
        messages = response.get("messages", [])
        if isinstance(messages, list):
            new_messages = len(messages)
            self.message_count = self._last_request_messages + new_messages

            # 从 usage_metadata 取真实 input_tokens（含 system + tools + messages）
            # input_tokens 在 LangChain 中对所有 provider 都是总量（含缓存），
            # 不需要额外加 cache_read / cache_write（否则会双重计算）
            for msg in reversed(messages):
                usage = getattr(msg, "usage_metadata", None)
                if usage:
                    input_tokens = usage.get("input_tokens", 0) or 0
                    if input_tokens > 0:
                        self.estimated_tokens = input_tokens
                        return

    def _estimate_tokens(self, messages: list) -> int:
        """估算消息的 token 数

        简单估算：每 4 个字符约 1 个 token（英文）
        中文每个字符约 1-2 个 token
        """
        total_chars = sum(self._extract_content_length(msg) for msg in messages)
        return total_chars // 2

    def _extract_content_length(self, msg) -> int:
        """提取消息内容长度"""
        content = msg.content if hasattr(msg, "content") else msg.get("content", "") if isinstance(msg, dict) else ""

        if isinstance(content, str):
            return len(content)

        if isinstance(content, list):
            return sum(
                len(block.get("text", "")) if isinstance(block, dict) else len(block)
                for block in content
                if isinstance(block, (dict, str))
            )

        return 0

    def is_near_limit(self, threshold: float = 0.8) -> bool:
        """是否接近上下文限制"""
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
