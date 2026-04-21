from __future__ import annotations

import importlib

import pytest

from backend.threads.events import reads as event_store_reads
from backend.threads.events import store as event_store


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


def test_build_run_event_read_transport_uses_repo_boundary() -> None:
    calls: list[tuple[str, tuple, dict]] = []

    class _Repo:
        def latest_run_id(self, thread_id: str) -> str | None:
            calls.append(("latest_run_id", (thread_id,), {}))
            return "run-1"

        def list_events(self, thread_id: str, run_id: str, *, after: int = 0, limit: int = 200):
            calls.append(("list_events", (thread_id, run_id), {"after": after, "limit": limit}))
            return [{"seq": 1, "event_type": "delta", "data": {"text": "hello"}}]

    transport = event_store_reads.build_run_event_read_transport(_Repo())

    assert transport.latest_run_id("thread-1") == "run-1"
    assert transport.list_events("thread-1", "run-1", after=3, limit=50) == [{"seq": 1, "event_type": "delta", "data": {"text": "hello"}}]
    assert calls == [
        ("latest_run_id", ("thread-1",), {}),
        ("list_events", ("thread-1", "run-1"), {"after": 3, "limit": 50}),
    ]


def test_run_event_store_write_owner_lives_under_backend_thread_runtime_events() -> None:
    owner_module = importlib.import_module("backend.threads.events.store")
    read_owner_module = importlib.import_module("backend.threads.events.reads")

    assert owner_module.__name__ == "backend.threads.events.store"
    assert hasattr(owner_module, "append_event")
    assert hasattr(owner_module, "read_events_after")
    assert hasattr(owner_module, "get_last_seq")
    assert hasattr(owner_module, "get_run_start_seq")
    assert hasattr(owner_module, "get_latest_run_id")
    assert hasattr(owner_module, "cleanup_old_runs")
    assert hasattr(read_owner_module, "build_run_event_read_transport")
