"""Token 使用量监控（6 项分项追踪）"""

from typing import Any

from .base import BaseMonitor


class TokenMonitor(BaseMonitor):
    """追踪 Token 使用量

    从 AIMessage 的 usage_metadata 中提取 token 统计（LangChain 统一格式），
    支持 6 项分项追踪：input / output / reasoning / cache_read / cache_write / total。
    当 usage_metadata 不可用时，回退到 response_metadata。
    """

    def __init__(self):
        self.call_count = 0
        # 6 项分项追踪
        self.input_tokens = 0  # 输入（排除缓存）
        self.output_tokens = 0  # 输出（排除推理）
        self.reasoning_tokens = 0  # 推理 token（o1/o3）
        self.cache_read_tokens = 0  # 缓存命中
        self.cache_write_tokens = 0  # 缓存写入
        self.total_tokens = 0  # 总计

        # 成本计算器（由 MonitorMiddleware 注入）
        self.cost_calculator = None

    def on_request(self, request: dict[str, Any]) -> None:
        """请求前：无操作（call_count 在 on_response 中计数）"""
        pass

    def on_response(self, request: dict[str, Any], response: dict[str, Any]) -> None:
        """响应后：从 usage_metadata 提取 token 统计，回退到 response_metadata"""
        messages = response.get("messages", [])
        if not isinstance(messages, list):
            messages = [messages]

        for msg in reversed(messages):
            # 优先使用 usage_metadata（LangChain 统一格式）
            usage = getattr(msg, "usage_metadata", None)
            if usage:
                self._extract_from_usage_metadata(usage)
                return

            # 回退到 response_metadata
            metadata = getattr(msg, "response_metadata", None)
            if metadata:
                self._extract_from_response_metadata(metadata)
                return

    def _extract_from_usage_metadata(self, usage: dict) -> None:
        """从 LangChain usage_metadata 提取分项数据"""
        input_total = usage.get("input_tokens", 0) or 0
        output_total = usage.get("output_tokens", 0) or 0
        total = usage.get("total_tokens", input_total + output_total) or 0

        input_details = usage.get("input_token_details", {}) or {}
        output_details = usage.get("output_token_details", {}) or {}

        cache_read = input_details.get("cache_read", 0) or 0
        cache_write = input_details.get("cache_creation", 0) or 0
        reasoning = output_details.get("reasoning", 0) or 0

        self.input_tokens += input_total - cache_read - cache_write
        self.output_tokens += output_total - reasoning
        self.reasoning_tokens += reasoning
        self.cache_read_tokens += cache_read
        self.cache_write_tokens += cache_write
        self.total_tokens += total
        self.call_count += 1

    def _extract_from_response_metadata(self, metadata: dict) -> None:
        """回退：从 response_metadata 提取（仅 input/output/total）"""
        usage = metadata.get("token_usage") or metadata.get("usage")
        if not usage:
            return

        prompt = usage.get("prompt_tokens") or usage.get("input_tokens", 0) or 0
        completion = usage.get("completion_tokens") or usage.get("output_tokens", 0) or 0
        total = usage.get("total_tokens", prompt + completion) or 0

        self.input_tokens += prompt
        self.output_tokens += completion
        self.total_tokens += total
        self.call_count += 1

    def get_cost(self) -> dict:
        """计算当前累计成本"""
        if not self.cost_calculator:
            return {"total": 0, "breakdown": {}}
        return self.cost_calculator.calculate(self.get_token_dict())

    def get_token_dict(self) -> dict:
        """返回 token 字典（供 CostCalculator 使用）"""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
        }

    # 向后兼容别名
    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens

    @property
    def completion_tokens(self) -> int:
        return self.output_tokens + self.reasoning_tokens

    def get_metrics(self) -> dict[str, Any]:
        cost = self.get_cost()
        return {
            "total_tokens": self.total_tokens,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            # 向后兼容
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "call_count": self.call_count,
            "cost": float(cost.get("total", 0)),
        }

    def reset(self) -> None:
        self.call_count = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.reasoning_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.total_tokens = 0
