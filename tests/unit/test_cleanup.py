"""Unit tests for core.runtime.cleanup CleanupRegistry."""

import asyncio
import signal

import pytest

from core.runtime.cleanup import CleanupRegistry


@pytest.mark.asyncio
async def test_runs_in_priority_order():
    order = []
    reg = CleanupRegistry()
    reg.register(lambda: order.append(3), priority=3)
    reg.register(lambda: order.append(1), priority=1)
    reg.register(lambda: order.append(2), priority=2)
    await reg.run_cleanup()
    assert order == [1, 2, 3]


@pytest.mark.asyncio
async def test_same_priority_runs_all():
    order = []
    reg = CleanupRegistry()
    reg.register(lambda: order.append("a"), priority=5)
    reg.register(lambda: order.append("b"), priority=5)
    await reg.run_cleanup()
    assert set(order) == {"a", "b"}


@pytest.mark.asyncio
async def test_failure_does_not_stop_later_functions():
    order = []
    reg = CleanupRegistry()

    def failing():
        raise RuntimeError("boom")

    reg.register(failing, priority=1)
    reg.register(lambda: order.append("ok"), priority=2)
    # Should not raise; failure is logged and execution continues
    await reg.run_cleanup()
    assert order == ["ok"]


@pytest.mark.asyncio
async def test_async_cleanup_function():
    results = []

    async def async_fn():
        results.append("async")

    reg = CleanupRegistry()
    reg.register(async_fn, priority=1)
    await reg.run_cleanup()
    assert results == ["async"]


@pytest.mark.asyncio
async def test_empty_registry_runs_cleanly():
    reg = CleanupRegistry()
    # Should complete without error
    await reg.run_cleanup()


@pytest.mark.asyncio
async def test_register_multiple_same_priority():
    order = []
    reg = CleanupRegistry()
    for i in range(5):
        n = i  # capture
        reg.register(lambda n=n: order.append(n), priority=1)
    await reg.run_cleanup()
    assert sorted(order) == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_register_returns_deregister_handle():
    order = []
    reg = CleanupRegistry()

    unregister = reg.register(lambda: order.append("gone"), priority=1)
    reg.register(lambda: order.append("kept"), priority=2)
    unregister()

    await reg.run_cleanup()

    assert order == ["kept"]


@pytest.mark.asyncio
async def test_slow_cleanup_function_times_out_and_later_functions_still_run():
    order = []
    reg = CleanupRegistry()

    async def slow():
        await asyncio.sleep(0.05)
        order.append("slow-finished")

    reg._timeout_s = 0.01
    reg.register(slow, priority=1)
    reg.register(lambda: order.append("later"), priority=2)

    await reg.run_cleanup()

    assert order == ["later"]


@pytest.mark.asyncio
async def test_same_priority_async_cleanups_run_concurrently():
    started = []
    release = asyncio.Event()
    reg = CleanupRegistry()

    async def first():
        started.append("first")
        await release.wait()

    async def second():
        started.append("second")
        await release.wait()

    reg.register(first, priority=1)
    reg.register(second, priority=1)

    task = asyncio.create_task(reg.run_cleanup())
    for _ in range(10):
        if len(started) == 2:
            break
        await asyncio.sleep(0)

    assert started == ["first", "second"]

    release.set()
    await task


@pytest.mark.asyncio
async def test_concurrent_run_cleanup_calls_do_not_double_run_entries():
    order = []
    release = asyncio.Event()
    reg = CleanupRegistry()

    async def slow():
        order.append("start")
        await release.wait()
        order.append("done")

    reg.register(slow, priority=1)

    first = asyncio.create_task(reg.run_cleanup())
    for _ in range(10):
        if order == ["start"]:
            break
        await asyncio.sleep(0)

    second = asyncio.create_task(reg.run_cleanup())
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)

    assert order == ["start", "done"]


@pytest.mark.asyncio
async def test_run_cleanup_marks_shutdown_in_progress_during_and_after_cleanup():
    seen = []
    release = asyncio.Event()
    reg = CleanupRegistry()

    async def slow():
        seen.append(reg.is_shutting_down())
        await release.wait()

    reg.register(slow, priority=1)

    task = asyncio.create_task(reg.run_cleanup())
    for _ in range(10):
        if seen:
            break
        await asyncio.sleep(0)

    assert seen == [True]
    assert reg.is_shutting_down() is True

    release.set()
    await task

    assert reg.is_shutting_down() is True


def test_setup_signal_handlers_includes_sighup_when_available(monkeypatch):
    registered = []

    class _FakeLoop:
        def add_signal_handler(self, sig, handler):
            registered.append(sig)

    monkeypatch.setattr(asyncio, "get_event_loop", lambda: _FakeLoop())

    CleanupRegistry()

    expected = {signal.SIGINT, signal.SIGTERM}
    if hasattr(signal, "SIGHUP"):
        expected.add(signal.SIGHUP)

    assert set(registered) == expected


def test_handle_signal_uses_registered_loop_without_requerying_event_loop(monkeypatch):
    scheduled = []

    class _FakeLoop:
        def add_signal_handler(self, sig, handler):
            return None

        def is_running(self):
            return True

        def create_task(self, coro):
            scheduled.append(coro)
            coro.close()

    fake_loop = _FakeLoop()
    monkeypatch.setattr(asyncio, "get_event_loop", lambda: fake_loop)
    reg = CleanupRegistry()

    def _boom():
        raise RuntimeError("no current loop")

    monkeypatch.setattr(asyncio, "get_event_loop", _boom)

    reg._handle_signal()

    assert len(scheduled) == 1


def test_handle_signal_runs_cleanup_immediately_when_registered_loop_is_not_running():
    called = []
    loop = asyncio.new_event_loop()

    try:
        asyncio.set_event_loop(loop)
        reg = CleanupRegistry()
        reg.register(lambda: called.append("ran"), priority=1)

        reg._handle_signal()

        assert called == ["ran"]
    finally:
        asyncio.set_event_loop(None)
        loop.close()
