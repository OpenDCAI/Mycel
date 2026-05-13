from __future__ import annotations

from typing import Any

from .base import BaseMonitor
from .cost import CostCalculator


class TokenMonitor(BaseMonitor):
    def __init__(self):
        self.call_count = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.reasoning_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.total_tokens = 0
        self.cost_calculator: CostCalculator | None = None

    def on_request(self, request: dict[str, Any]) -> None:
        pass

    def on_response(self, request: dict[str, Any], response: dict[str, Any]) -> None:
        messages = response.get("messages", [])
        if not isinstance(messages, list):
            messages = [messages]

        for msg in reversed(messages):
            usage = getattr(msg, "usage_metadata", None)
            if usage:
                self._extract_from_usage_metadata(usage)
                return

            metadata = getattr(msg, "response_metadata", None)
            if metadata:
                self._extract_from_response_metadata(metadata)
                return

    def _extract_from_usage_metadata(self, usage: dict) -> None:
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
        if not self.cost_calculator:
            return {"total": 0, "breakdown": {}}
        return self.cost_calculator.calculate(self.get_token_dict())

    def get_token_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
        }

    def get_metrics(self) -> dict[str, Any]:
        cost = self.get_cost()
        return {
            "total_tokens": self.total_tokens,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
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
