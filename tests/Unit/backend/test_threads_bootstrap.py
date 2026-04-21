from types import SimpleNamespace

from backend.threads import bootstrap as threads_bootstrap


def test_attach_threads_runtime_wires_runtime_dependencies(monkeypatch):
    queue_repo = object()
    queue_manager = object()
    gateway = object()
    seen: list[tuple[str, object]] = []

    storage_container = SimpleNamespace(queue_repo=lambda: queue_repo)
    app = SimpleNamespace(state=SimpleNamespace())

    monkeypatch.setattr(
        threads_bootstrap,
        "MessageQueueManager",
        lambda *, repo: seen.append(("queue_manager", repo)) or queue_manager,
    )
    monkeypatch.setattr(
        threads_bootstrap,
        "build_agent_runtime_gateway",
        lambda target_app: seen.append(("gateway", target_app)) or gateway,
    )

    threads_bootstrap.attach_threads_runtime(app, storage_container)

    assert app.state.queue_manager is queue_manager
    assert app.state.agent_pool == {}
    assert app.state.thread_sandbox == {}
    assert app.state.thread_cwd == {}
    assert app.state.thread_tasks == {}
    assert app.state.thread_event_buffers == {}
    assert app.state.subagent_buffers == {}
    assert app.state.thread_last_active == {}
    assert app.state.agent_runtime_gateway is gateway
    assert seen == [
        ("queue_manager", queue_repo),
        ("gateway", app),
    ]
    assert hasattr(app.state, "thread_locks_guard")
    assert hasattr(app.state, "thread_locks")
