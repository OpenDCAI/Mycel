from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest

from backend.monitor_app import lifespan as monitor_app_lifespan
from backend.web.core import lifespan as web_lifespan


def test_resource_refresh_loop_moves_from_web_lifespan_to_monitor_app_lifespan():
    monitor_source = inspect.getsource(monitor_app_lifespan)
    web_source = inspect.getsource(web_lifespan)

    assert "resource_overview_refresh_loop" in monitor_source
    assert "monitor_resources_task" in monitor_source
    assert "resource_overview_refresh_loop" not in web_source
    assert "monitor_resources_task" not in web_source


@pytest.mark.asyncio
async def test_monitor_app_lifespan_starts_and_cancels_resource_refresh_loop(monkeypatch: pytest.MonkeyPatch):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def _loop():
        started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(monitor_app_lifespan, "resource_overview_refresh_loop", _loop)
    monkeypatch.setattr(monitor_app_lifespan, "build_runtime_storage_state", lambda: object())

    app = SimpleNamespace(state=SimpleNamespace())

    async with monitor_app_lifespan.lifespan(app):
        await asyncio.wait_for(started.wait(), timeout=1)
        assert app.state.monitor_resources_task is not None
        assert not app.state.monitor_resources_task.done()

    await asyncio.wait_for(cancelled.wait(), timeout=1)


@pytest.mark.asyncio
async def test_monitor_app_lifespan_requires_storage_runtime_contract(monkeypatch: pytest.MonkeyPatch):
    def _raise():
        raise RuntimeError("Supabase storage requires runtime config.")

    monkeypatch.setattr(monitor_app_lifespan, "build_runtime_storage_state", _raise)

    app = SimpleNamespace(state=SimpleNamespace())

    with pytest.raises(RuntimeError, match="Supabase storage requires runtime config."):
        async with monitor_app_lifespan.lifespan(app):
            raise AssertionError("lifespan should fail before yielding")
