import asyncio
from collections import deque
from dataclasses import dataclass, field


@dataclass
class RunEventBuffer:
    events: list[dict] = field(default_factory=list)
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    _notify: asyncio.Condition = field(default_factory=asyncio.Condition)
    run_id: str = ""

    async def put(self, event: dict) -> None:
        self.events.append(event)
        async with self._notify:
            self._notify.notify_all()

    async def mark_done(self) -> None:
        self.finished.set()
        async with self._notify:
            self._notify.notify_all()

    async def read(self, cursor: int) -> tuple[list[dict], int]:
        while True:
            if cursor < len(self.events):
                new = self.events[cursor:]
                return new, len(self.events)
            if self.finished.is_set():
                return [], cursor
            async with self._notify:
                await self._notify.wait()

    async def read_with_timeout(self, cursor: int, timeout: float = 30) -> tuple[list[dict] | None, int]:
        if cursor < len(self.events):
            return self.events[cursor:], len(self.events)
        if self.finished.is_set():
            return [], cursor
        async with self._notify:
            try:
                await asyncio.wait_for(self._notify.wait(), timeout)
            except TimeoutError:
                return None, cursor
        # @@@post-wait-done - mark_done may arrive while waiting; return completion sentinel, not timeout sentinel.
        if cursor < len(self.events):
            return self.events[cursor:], len(self.events)
        if self.finished.is_set():
            return [], cursor
        return None, cursor


@dataclass
class ThreadEventBuffer:
    _ring: deque[dict] = field(default_factory=lambda: deque(maxlen=2000))
    _notify: asyncio.Condition = field(default_factory=asyncio.Condition)
    _total_count: int = 0  # monotonic counter (total events ever put)
    # @@@thread-buffer-never-finishes - keep the same observer protocol surface
    # as RunEventBuffer, but thread buffers never mark completion.
    finished: asyncio.Event = field(default_factory=asyncio.Event)

    async def put(self, event: dict) -> None:
        self._ring.append(event)
        self._total_count += 1
        async with self._notify:
            self._notify.notify_all()

    async def read_with_timeout(self, cursor: int, timeout: float = 30) -> tuple[list[dict] | None, int]:
        avail_start = self._total_count - len(self._ring)
        if cursor < avail_start:
            events = list(self._ring)
            return events, self._total_count
        offset = cursor - avail_start
        if offset < len(self._ring):
            events = list(self._ring)[offset:]
            return events, self._total_count
        async with self._notify:
            try:
                await asyncio.wait_for(self._notify.wait(), timeout)
            except TimeoutError:
                return None, cursor
        avail_start = self._total_count - len(self._ring)
        if cursor < avail_start:
            return list(self._ring), self._total_count
        offset = cursor - avail_start
        if offset < len(self._ring):
            return list(self._ring)[offset:], self._total_count
        return None, cursor

    @property
    def total_count(self) -> int:
        return self._total_count
