from __future__ import annotations

from types import SimpleNamespace

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


class _Repo:
    def __init__(self, rows: dict[str, object]) -> None:
        self.rows = rows

    def get_by_id(self, row_id: str):
        return self.rows.get(row_id)


def _make_app(*, thread_repo, workspace_repo=None, sandbox_repo=None):
    queue_manager = SimpleNamespace(clear_all=lambda _thread_id: None)
    return SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=thread_repo,
            workspace_repo=workspace_repo or _Repo({}),
            sandbox_repo=sandbox_repo or _Repo({}),
            thread_sandbox={"thread-1": "local"},
            thread_cwd={"thread-1": "/workspace"},
            thread_event_buffers={"thread-1": object()},
            thread_tasks={"thread-1": object()},
            thread_last_active={"thread-1": 1.0},
            agent_pool={"thread-1:local": object()},
            queue_manager=queue_manager,
        )
    )


def test_converge_owner_thread_runtime_accepts_workspace_sandbox_binding_without_terminal(monkeypatch) -> None:
    thread_repo = _FakeThreadRepo(
        {
            "thread-1": {
                "agent_user_id": "agent-1",
                "owner_user_id": "owner-1",
                "current_workspace_id": "workspace-1",
            }
        }
    )
    app = _make_app(
        thread_repo=thread_repo,
        workspace_repo=_Repo(
            {
                "workspace-1": SimpleNamespace(
                    id="workspace-1",
                    owner_user_id="owner-1",
                    sandbox_id="sandbox-1",
                    workspace_path="/workspace",
                )
            }
        ),
        sandbox_repo=_Repo(
            {
                "sandbox-1": SimpleNamespace(
                    id="sandbox-1",
                    owner_user_id="owner-1",
                    provider_name="daytona",
                    config={"legacy_lease_id": "lease-1"},
                )
            }
        ),
    )

    monkeypatch.setattr(
        "backend.web.services.thread_runtime_convergence.delete_thread_in_db",
        lambda _thread_id: (_ for _ in ()).throw(AssertionError("purge should not run when runtime binding exists")),
    )

    result = converge_owner_thread_runtime(app, "thread-1")

    assert result == "ready"
    assert thread_repo.deleted == []


def test_converge_owner_thread_runtime_purges_thread_without_workspace_binding(monkeypatch) -> None:
    purged: list[str] = []
    thread_repo = _FakeThreadRepo({"thread-1": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"}})
    app = _make_app(thread_repo=thread_repo)

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


def test_summarize_owner_thread_runtime_uses_workspace_sandbox_binding(monkeypatch) -> None:
    purged: list[str] = []
    app = _make_app(
        thread_repo=_FakeThreadRepo(
            {
                "thread-1": {
                    "agent_user_id": "agent-1",
                    "owner_user_id": "owner-1",
                    "current_workspace_id": "workspace-1",
                },
                "broken-thread": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"},
            }
        ),
        workspace_repo=_Repo(
            {
                "workspace-1": SimpleNamespace(
                    id="workspace-1",
                    owner_user_id="owner-1",
                    sandbox_id="sandbox-1",
                    workspace_path="/workspace",
                )
            }
        ),
        sandbox_repo=_Repo(
            {
                "sandbox-1": SimpleNamespace(
                    id="sandbox-1",
                    owner_user_id="owner-1",
                    provider_name="daytona",
                    config={"legacy_lease_id": "lease-1"},
                )
            }
        ),
    )
    monkeypatch.setattr(
        "backend.web.services.thread_runtime_convergence.delete_thread_in_db",
        lambda thread_id: purged.append(thread_id),
    )

    assert summarize_owner_thread_runtime(app, ["thread-1", "broken-thread"]) == {
        "thread-1": "ready",
        "broken-thread": "purged",
    }
    assert purged == ["broken-thread"]
