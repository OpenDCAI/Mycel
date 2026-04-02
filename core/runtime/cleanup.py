"""CleanupRegistry — priority-ordered async cleanup for LeonAgent lifecycle.

Aligned with CC Pattern 5: Lifecycle & Cleanup.
Priority numbers: lower = runs first.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Callable, Awaitable
from itertools import groupby

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
        self._timeout_s = 2.0
        self._cleanup_task: asyncio.Task[None] | None = None
        self._shutdown_in_progress = False
        self._signal_loop: asyncio.AbstractEventLoop | None = None
        self._setup_signal_handlers()

    def register(self, fn: Callable[[], Awaitable[None] | None], priority: int = 5) -> Callable[[], None]:
        """Register a cleanup function.

        Args:
            fn: Sync or async callable that releases resources.
            priority: Execution order — lower number runs first (1 before 2).
        """
        entry = (priority, fn)
        self._entries.append(entry)

        def unregister() -> None:
            try:
                self._entries.remove(entry)
            except ValueError:
                return

        return unregister

    async def run_cleanup(self) -> None:
        """Execute all registered cleanup functions in priority order.

        Different priority tiers run in order. Entries inside the same priority
        tier run concurrently so one slow cleanup does not serialize its peers.
        """
        if self._cleanup_task is not None:
            await asyncio.shield(self._cleanup_task)
            return

        async def _run_all() -> None:
            sorted_entries = sorted(self._entries, key=lambda x: x[0])
            for priority, grouped_entries in groupby(sorted_entries, key=lambda x: x[0]):
                await asyncio.gather(
                    *(self._run_entry(priority, fn) for _, fn in grouped_entries),
                    return_exceptions=True,
                )

        self._shutdown_in_progress = True
        self._cleanup_task = asyncio.create_task(_run_all())
        await asyncio.shield(self._cleanup_task)

    def is_shutting_down(self) -> bool:
        return self._shutdown_in_progress

    async def _run_entry(self, priority: int, fn: Callable[[], Awaitable[None] | None]) -> None:
        try:
            result = fn()
            if asyncio.iscoroutine(result):
                await asyncio.wait_for(result, timeout=self._timeout_s)
        except asyncio.TimeoutError:
            logger.warning("CleanupRegistry: cleanup fn %s timed out after %.2fs", fn, self._timeout_s)
        except Exception:
            logger.exception("CleanupRegistry: error in cleanup fn %s (priority=%d)", fn, priority)

    def _setup_signal_handlers(self) -> None:
        """Register SIGINT/SIGTERM handlers to trigger async cleanup."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return  # No running loop yet — signal handlers set up later
        self._signal_loop = loop

        signals = [signal.SIGINT, signal.SIGTERM]
        if hasattr(signal, "SIGHUP"):
            signals.append(signal.SIGHUP)

        for sig in signals:
            try:
                loop.add_signal_handler(sig, self._handle_signal)
            except (NotImplementedError, RuntimeError):
                # Windows or non-main thread — skip signal handler setup
                pass

    def _handle_signal(self) -> None:
        loop = self._signal_loop
        if loop is None:
            return
        if loop.is_running():
            loop.create_task(self.run_cleanup())
            return
        loop.run_until_complete(self.run_cleanup())
