from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.web.services.thread_runtime_convergence import converge_owner_thread_runtime, summarize_owner_thread_runtime


class _FakeThreadRepo:
    def __init__(self, rows: dict[str, dict]) -> None:
        self.rows = dict(rows)
        self.deleted: list[str] = []

    def get_by_id(self, thread_id: str):
        row = self.rows.get(thread_id)
        if row is None:
            return None
        return {"id": thread_id, **row}

    def delete(self, thread_id: str) -> None:
        self.deleted.append(thread_id)
        self.rows.pop(thread_id, None)


class _FakeTerminalRepo:
    def __init__(self, *, active_by_thread=None, terminals_by_thread=None) -> None:
        self._active_by_thread = dict(active_by_thread or {})
        self._terminals_by_thread = {key: list(value) for key, value in (terminals_by_thread or {}).items()}
        self.set_active_calls: list[tuple[str, str]] = []

    def get_active(self, thread_id: str):
        return self._active_by_thread.get(thread_id)

    def list_by_thread(self, thread_id: str):
        return list(self._terminals_by_thread.get(thread_id, []))

    def set_active(self, thread_id: str, terminal_id: str) -> None:
        self.set_active_calls.append((thread_id, terminal_id))
        for row in self._terminals_by_thread.get(thread_id, []):
            if str(row["terminal_id"]) == terminal_id:
                self._active_by_thread[thread_id] = row
                break

    def summarize_threads(self, thread_ids: list[str]):
        summary: dict[str, dict[str, str | None]] = {}
        for thread_id in thread_ids:
            active = self._active_by_thread.get(thread_id)
            terminals = self._terminals_by_thread.get(thread_id, [])
            summary[thread_id] = {
                "active_terminal_id": str(active["terminal_id"]) if active is not None else None,
                "latest_terminal_id": str(terminals[0]["terminal_id"]) if terminals else None,
            }
        return summary


def _make_app(*, thread_repo, terminal_repo):
    queue_manager = SimpleNamespace(clear_all=lambda _thread_id: None)
    return SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=thread_repo,
            terminal_repo=terminal_repo,
            thread_sandbox={"thread-1": "local"},
            thread_cwd={"thread-1": "/workspace"},
            thread_event_buffers={"thread-1": object()},
            thread_tasks={"thread-1": object()},
            thread_last_active={"thread-1": 1.0},
            agent_pool={"thread-1:local": object()},
            queue_manager=queue_manager,
        )
    )


def test_converge_owner_thread_runtime_repairs_missing_pointer_from_latest_terminal(monkeypatch) -> None:
    thread_repo = _FakeThreadRepo({"thread-1": {"agent_user_id": "agent-1"}})
    terminal_repo = _FakeTerminalRepo(
        terminals_by_thread={
            "thread-1": [
                {"terminal_id": "term-new", "lease_id": "lease-1"},
                {"terminal_id": "term-old", "lease_id": "lease-1"},
            ]
        }
    )
    app = _make_app(thread_repo=thread_repo, terminal_repo=terminal_repo)

    monkeypatch.setattr(
        "backend.web.services.thread_runtime_convergence.delete_thread_in_db",
        lambda _thread_id: (_ for _ in ()).throw(AssertionError("purge should not run when terminals still exist")),
    )

    result = converge_owner_thread_runtime(app, "thread-1")

    assert result == "repaired_pointer"
    assert terminal_repo.set_active_calls == [("thread-1", "term-new")]
    assert thread_repo.deleted == []


def test_converge_owner_thread_runtime_purges_incomplete_thread_without_terminals(monkeypatch) -> None:
    purged: list[str] = []
    thread_repo = _FakeThreadRepo({"thread-1": {"agent_user_id": "agent-1"}})
    terminal_repo = _FakeTerminalRepo()
    app = _make_app(thread_repo=thread_repo, terminal_repo=terminal_repo)

    monkeypatch.setattr(
        "backend.web.services.thread_runtime_convergence.delete_thread_in_db",
        lambda thread_id: purged.append(thread_id),
    )

    result = converge_owner_thread_runtime(app, "thread-1")

    assert result == "purged"
    assert purged == ["thread-1"]
    assert thread_repo.deleted == ["thread-1"]
    assert "thread-1" not in app.state.thread_sandbox
    assert "thread-1" not in app.state.thread_cwd
    assert "thread-1" not in app.state.thread_event_buffers
    assert "thread-1" not in app.state.thread_tasks
    assert "thread-1" not in app.state.thread_last_active
    assert app.state.agent_pool == {}


def test_summarize_owner_thread_runtime_requires_batch_summary_contract() -> None:
    app = _make_app(
        thread_repo=_FakeThreadRepo({"thread-1": {"agent_user_id": "agent-1"}}),
        terminal_repo=SimpleNamespace(),
    )

    with pytest.raises(RuntimeError, match="terminal_repo must support summarize_threads for owner runtime convergence"):
        summarize_owner_thread_runtime(app, ["thread-1"])
