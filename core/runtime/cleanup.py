"""CleanupRegistry — priority-ordered async cleanup for LeonAgent lifecycle.

Aligned with CC Pattern 5: Lifecycle & Cleanup.
Priority numbers: lower = runs first.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Callable, Awaitable

logger = logging.getLogger(__name__)


class CleanupRegistry:
    """Registry of async cleanup functions executed in priority order on shutdown.

    Usage:
        registry = CleanupRegistry()
        registry.register(close_db, priority=1)
        registry.register(close_sandbox, priority=2)
        await registry.run_cleanup()
    """

    def __init__(self):
        # List of (priority, fn) — not a dict because same priority can have multiple fns
        self._entries: list[tuple[int, Callable[[], Awaitable[None] | None]]] = []
        self._setup_signal_handlers()

    def register(self, fn: Callable[[], Awaitable[None] | None], priority: int = 5) -> None:
        """Register a cleanup function.

        Args:
            fn: Sync or async callable that releases resources.
            priority: Execution order — lower number runs first (1 before 2).
        """
        self._entries.append((priority, fn))

    async def run_cleanup(self) -> None:
        """Execute all registered cleanup functions in priority order.

        Runs sequentially (not gathered) so failures are isolated.
        A failing function is logged but does not prevent later functions from running.
        """
        sorted_entries = sorted(self._entries, key=lambda x: x[0])
        for priority, fn in sorted_entries:
            try:
                result = fn()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("CleanupRegistry: error in cleanup fn %s (priority=%d)", fn, priority)

    def _setup_signal_handlers(self) -> None:
        """Register SIGINT/SIGTERM handlers to trigger async cleanup."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return  # No running loop yet — signal handlers set up later

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._handle_signal)
            except (NotImplementedError, RuntimeError):
                # Windows or non-main thread — skip signal handler setup
                pass

    def _handle_signal(self) -> None:
        loop = asyncio.get_event_loop()
        loop.create_task(self.run_cleanup())
