from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.monitor.app import lifespan as monitor_app_lifespan


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
    monkeypatch.setattr(monitor_app_lifespan, "attach_runtime_storage_state", lambda _app: object())

    app = SimpleNamespace(state=SimpleNamespace())

    async with monitor_app_lifespan.lifespan(app):
        await asyncio.wait_for(started.wait(), timeout=1)
        assert app.state.monitor_resources_task is not None
        assert not app.state.monitor_resources_task.done()

    await asyncio.wait_for(cancelled.wait(), timeout=1)


@pytest.mark.asyncio
async def test_monitor_app_lifespan_requires_storage_runtime_contract(monkeypatch: pytest.MonkeyPatch):
    def _raise(_app):
        raise RuntimeError("Supabase storage requires runtime config.")

    monkeypatch.setattr(monitor_app_lifespan, "attach_runtime_storage_state", _raise)

    app = SimpleNamespace(state=SimpleNamespace())

    with pytest.raises(RuntimeError, match="Supabase storage requires runtime config."):
        async with monitor_app_lifespan.lifespan(app):
            raise AssertionError("lifespan should fail before yielding")
