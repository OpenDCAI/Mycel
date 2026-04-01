"""Unit tests for core.runtime.cleanup CleanupRegistry."""

import asyncio

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
