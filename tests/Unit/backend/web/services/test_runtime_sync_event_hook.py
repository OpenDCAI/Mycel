from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine, Iterator
from typing import Any

import pytest

from backend.threads.chat_adapters.runtime_sync_event_hook import make_blocking_runtime_event_hook


class LoopThread:
    def __init__(self) -> None:
        self.loop_ready: threading.Event = threading.Event()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        assert self.loop_ready.wait(1)

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.loop = loop
        self.loop_ready.set()
        loop.run_forever()
        loop.close()

    def run(self, coroutine: Coroutine[Any, Any, Any]) -> Any:
        loop = self.loop
        assert loop is not None
        return asyncio.run_coroutine_threadsafe(coroutine, loop).result(timeout=1)

    def close(self) -> None:
        loop = self.loop
        assert loop is not None
        loop.call_soon_threadsafe(loop.stop)
        self.thread.join(timeout=1)


@pytest.fixture
def loop_thread() -> Iterator[LoopThread]:
    thread = LoopThread()
    try:
        yield thread
    finally:
        thread.close()


def test_blocking_runtime_event_hook_blocks_producer_until_dispatch_completes(loop_thread: LoopThread) -> None:
    dispatch_started = threading.Event()
    release_dispatch = threading.Event()
    producer_done = threading.Event()
    producer_error: list[BaseException] = []

    async def make_hook():
        async def dispatch_event(value: str) -> int:
            dispatch_started.set()
            await asyncio.to_thread(release_dispatch.wait)
            return len(value)

        return make_blocking_runtime_event_hook(dispatch_event)

    hook = loop_thread.run(make_hook())

    def run_producer() -> None:
        try:
            assert hook("event-1") is None
        except BaseException as exc:
            producer_error.append(exc)
        finally:
            producer_done.set()

    producer = threading.Thread(target=run_producer)
    producer.start()

    assert dispatch_started.wait(1)
    assert not producer_done.wait(0.05)

    release_dispatch.set()
    producer.join(timeout=1)

    assert producer_done.is_set()
    assert producer_error == []


def test_blocking_runtime_event_hook_raises_dispatch_failure_in_producer(loop_thread: LoopThread) -> None:
    async def make_hook():
        async def dispatch_event(_value: str) -> None:
            raise RuntimeError("runtime offline")

        return make_blocking_runtime_event_hook(dispatch_event)

    hook = loop_thread.run(make_hook())

    with pytest.raises(RuntimeError) as exc_info:
        hook("event-1")

    assert str(exc_info.value) == "runtime offline"


def test_blocking_runtime_event_hook_refuses_owner_loop_thread(loop_thread: LoopThread) -> None:
    async def make_and_call_hook() -> None:
        async def dispatch_event(_value: str) -> None:
            raise AssertionError("dispatch should not run on owner loop")

        hook = make_blocking_runtime_event_hook(dispatch_event)
        hook("event-1")

    with pytest.raises(RuntimeError) as exc_info:
        loop_thread.run(make_and_call_hook())

    assert str(exc_info.value) == "Blocking runtime event hook cannot run on its owner event loop thread"
