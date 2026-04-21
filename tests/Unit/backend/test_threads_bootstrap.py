from types import SimpleNamespace

import pytest

from backend.threads import bootstrap as threads_bootstrap


def test_attach_threads_runtime_wires_runtime_dependencies(monkeypatch):
    queue_repo = object()
    queue_manager = object()
    gateway = object()
    activity_reader = object()
    typing_tracker = object()
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
        "build_agent_runtime_state",
        lambda target_app, *, typing_tracker: (
            seen.append(("runtime_state", target_app))
            or seen.append(("typing_tracker", typing_tracker))
            or SimpleNamespace(gateway=gateway, activity_reader=activity_reader)
        ),
    )

    state = threads_bootstrap.attach_threads_runtime(app, storage_container, typing_tracker=typing_tracker)

    assert app.state.queue_manager is queue_manager
    assert app.state.agent_pool == {}
    assert app.state.thread_sandbox == {}
    assert app.state.thread_cwd == {}
    assert app.state.thread_tasks == {}
    assert app.state.thread_event_buffers == {}
    assert app.state.subagent_buffers == {}
    assert app.state.thread_last_active == {}
    assert app.state.agent_runtime_gateway is gateway
    assert state.queue_manager is queue_manager
    assert state.agent_runtime_gateway is gateway
    assert state.activity_reader is activity_reader
    assert seen == [
        ("queue_manager", queue_repo),
        ("runtime_state", app),
        ("typing_tracker", typing_tracker),
    ]
    assert hasattr(app.state, "thread_locks_guard")
    assert hasattr(app.state, "thread_locks")


def test_attach_threads_runtime_requires_explicit_typing_tracker():
    app = SimpleNamespace(state=SimpleNamespace())
    storage_container = SimpleNamespace(queue_repo=lambda: object())

    with pytest.raises(TypeError, match="typing_tracker"):
        threads_bootstrap.attach_threads_runtime(app, storage_container)
