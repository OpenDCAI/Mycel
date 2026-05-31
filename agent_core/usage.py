"""Token usage accounting + optional cost pricing.

Provider-agnostic: the loop records token counts from each response's
``usage_metadata``. Cost (USD) is opt-in via a ``pricer`` callable so the core
carries no provider price tables.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Pricer = Callable[[int, int], float]  # (input_tokens, output_tokens) -> usd


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    turns: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def token_pricer(input_per_1k: float, output_per_1k: float) -> Pricer:
    """A simple linear pricer from per-1K-token rates."""

    def price(input_tokens: int, output_tokens: int) -> float:
        return input_tokens / 1000 * input_per_1k + output_tokens / 1000 * output_per_1k

    return price


class UsageMeter:
    def __init__(self, pricer: Pricer | None = None) -> None:
        self.usage = Usage()
        self._pricer = pricer

    def record(self, *, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self.usage.input_tokens += input_tokens
        self.usage.output_tokens += output_tokens
        self.usage.turns += 1
        if self._pricer is not None:
            self.usage.cost_usd += self._pricer(input_tokens, output_tokens)

    def record_message(self, ai_msg: Any) -> None:
        """Pull token counts off a LangChain AIMessage's usage_metadata, if present."""
        meta = getattr(ai_msg, "usage_metadata", None)
        if not isinstance(meta, dict):
            return
        self.record(
            input_tokens=int(meta.get("input_tokens", 0) or 0),
            output_tokens=int(meta.get("output_tokens", 0) or 0),
        )
