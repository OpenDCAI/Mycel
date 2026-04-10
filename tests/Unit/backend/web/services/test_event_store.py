from __future__ import annotations

import pytest

from backend.web.services import event_store


@pytest.mark.asyncio
async def test_append_event_fails_loudly_when_default_run_event_repo_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(event_store, "_default_run_event_repo", None)
    monkeypatch.setattr(
        event_store,
        "build_storage_container",
        lambda: (_ for _ in ()).throw(RuntimeError("run event repo unavailable")),
    )

    with pytest.raises(RuntimeError, match="run event repo unavailable"):
        await event_store.append_event(
            "thread-1",
            "run-1",
            {"event": "delta", "data": {"text": "hello"}},
        )


@pytest.mark.asyncio
async def test_read_events_after_fails_loudly_when_default_run_event_repo_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(event_store, "_default_run_event_repo", None)
    monkeypatch.setattr(
        event_store,
        "build_storage_container",
        lambda: (_ for _ in ()).throw(RuntimeError("run event repo unavailable")),
    )

    with pytest.raises(RuntimeError, match="run event repo unavailable"):
        await event_store.read_events_after("thread-1", "run-1")
