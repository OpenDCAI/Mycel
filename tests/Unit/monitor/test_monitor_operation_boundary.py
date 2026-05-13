from backend.monitor.infrastructure.persistence import operation_repo as monitor_operation_repo_impl


def test_default_monitor_operation_repo_uses_storage_container_boundary(monkeypatch):
    repo = object()

    class _Container:
        def monitor_operation_repo(self):
            return repo

    monkeypatch.setattr(monitor_operation_repo_impl, "_default_monitor_operation_repo", None)
    monkeypatch.setattr(monitor_operation_repo_impl, "build_storage_container", lambda: _Container())

    assert monitor_operation_repo_impl.default_monitor_operation_repo() is repo


def test_default_monitor_operation_repo_fails_loudly_when_storage_repo_is_unavailable(monkeypatch):
    monkeypatch.setattr(monitor_operation_repo_impl, "_default_monitor_operation_repo", None)
    monkeypatch.setattr(
        monitor_operation_repo_impl,
        "build_storage_container",
        lambda: (_ for _ in ()).throw(RuntimeError("monitor operation repo unavailable")),
    )

    try:
        monitor_operation_repo_impl.default_monitor_operation_repo()
    except RuntimeError as exc:
        assert str(exc) == "monitor operation repo unavailable"
    else:
        raise AssertionError("expected RuntimeError")
