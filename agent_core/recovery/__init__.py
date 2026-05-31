"""Optional recovery layers.

The original loop baked a 6-strategy error-recovery state machine into its hot
path. Here recovery is opt-in middleware: add what you need, skip what you don't.
``RetryMiddleware`` is the canonical example (transient model-call retries).
"""

from __future__ import annotations

from agent_core.recovery.retry import RetryMiddleware

__all__ = ["RetryMiddleware"]
