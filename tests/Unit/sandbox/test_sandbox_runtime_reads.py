from __future__ import annotations

from types import SimpleNamespace

from backend.sandboxes.runtime.reads import load_all_sandbox_runtimes


def test_load_all_sandbox_runtimes_collapses_duplicate_session_rows_to_visible_owner_thread() -> None:
    manager = SimpleNamespace(
        list_sessions=lambda: [
            {
                "session_id": "sess-1",
                "thread_id": "subagent-deadbeef",
                "provider": "local",
                "status": "running",
                "created_at": "2026-04-22T10:00:00",
                "last_active": "2026-04-22T10:01:00",
                "sandbox_runtime_id": "runtime-1",
                "instance_id": "sess-1",
                "source": "runtime",
                "inspect_visible": True,
            },
            {
                "session_id": "sess-1",
                "thread_id": "thread-main",
                "provider": "local",
                "status": "running",
                "created_at": "2026-04-22T10:00:00",
                "last_active": "2026-04-22T10:02:00",
                "sandbox_runtime_id": "runtime-1",
                "instance_id": "sess-1",
                "chat_session_id": "chat-1",
                "source": "runtime",
                "inspect_visible": True,
            },
        ]
    )

    rows = load_all_sandbox_runtimes({"local": manager})

    assert rows == [
        {
            "session_id": "sess-1",
            "thread_id": "thread-main",
            "provider": "local",
            "status": "running",
            "created_at": "2026-04-22T10:00:00",
            "last_active": "2026-04-22T10:02:00",
            "sandbox_runtime_id": "runtime-1",
            "instance_id": "sess-1",
            "chat_session_id": "chat-1",
            "source": "runtime",
            "inspect_visible": True,
        }
    ]
