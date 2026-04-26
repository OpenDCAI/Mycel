from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.monitor.app import lifespan as monitor_app_lifespan


@pytest.mark.asyncio
async def test_monitor_app_lifespan_starts_and_cancels_resource_refresh_loop(monkeypatch: pytest.MonkeyPatch):
    started = asyncio.Event()
    cancelled = asyncio.Event()
    auth_calls = []
    user_repo = object()
    contact_repo = object()

    async def _loop():
        started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monitor_storage = SimpleNamespace(
        storage_container=SimpleNamespace(user_repo=lambda: user_repo, contact_repo=lambda: contact_repo),
    )

    monkeypatch.setattr(monitor_app_lifespan, "resource_overview_refresh_loop", _loop)
    monkeypatch.setattr(monitor_app_lifespan, "attach_runtime_storage_state", lambda _app: monitor_storage)
    monkeypatch.setattr(
        monitor_app_lifespan,
        "attach_auth_runtime_state",
        lambda _app, *, storage_state, contact_repo: auth_calls.append((storage_state, contact_repo)) or object(),
    )

    app = SimpleNamespace(state=SimpleNamespace())

    async with monitor_app_lifespan.lifespan(app):
        await asyncio.wait_for(started.wait(), timeout=1)
        assert app.state.user_repo is user_repo

    await asyncio.wait_for(cancelled.wait(), timeout=1)
    assert auth_calls == [(monitor_storage, contact_repo)]


@pytest.mark.asyncio
async def test_monitor_app_lifespan_requires_storage_runtime_contract(monkeypatch: pytest.MonkeyPatch):
    def _raise(_app):
        raise RuntimeError("Supabase storage requires runtime config.")

    monkeypatch.setattr(monitor_app_lifespan, "attach_runtime_storage_state", _raise)

    app = SimpleNamespace(state=SimpleNamespace())

    with pytest.raises(RuntimeError, match="Supabase storage requires runtime config."):
        async with monitor_app_lifespan.lifespan(app):
            raise AssertionError("lifespan should fail before yielding")
