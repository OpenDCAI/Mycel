"""RetryMiddleware — retry transient model-call failures with linear backoff.

Place it ahead of ``ToolRunner`` in the middleware list so it wraps the actual
model call. Opt-in: agents that don't want retries simply omit it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from agent_core.middleware import AgentMiddleware, ModelRequest, ModelResponse

logger = logging.getLogger(__name__)


class RetryMiddleware(AgentMiddleware):
    def __init__(
        self,
        *,
        max_retries: int = 2,
        retry_on: tuple[type[BaseException], ...] = (Exception,),
        base_delay: float = 0.0,
    ) -> None:
        self.max_retries = max_retries
        self.retry_on = retry_on
        self.base_delay = base_delay

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        attempt = 0
        while True:
            try:
                return await handler(request)
            except self.retry_on as exc:  # noqa: BLE001 - retry policy is intentional
                attempt += 1
                if attempt > self.max_retries:
                    raise
                logger.warning("model call failed (attempt %d/%d): %s; retrying", attempt, self.max_retries, exc)
                if self.base_delay:
                    await asyncio.sleep(self.base_delay * attempt)
