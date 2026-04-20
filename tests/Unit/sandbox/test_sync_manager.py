from types import SimpleNamespace

import sandbox.sync.manager as sync_manager_module


def test_sync_manager_uses_process_local_backing_for_remote_runtime() -> None:
    manager = sync_manager_module.SyncManager(provider_capability=SimpleNamespace(runtime_kind="remote_pty"))

    assert type(manager.strategy).__name__ == "IncrementalSyncStrategy"


def test_sync_manager_uses_sync_state_default_backing_for_remote_runtime(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _SyncStateProbe:
        def __init__(self, repo=None) -> None:
            captured["repo"] = repo

    monkeypatch.setattr("sandbox.sync.state.SyncState", _SyncStateProbe)

    manager = sync_manager_module.SyncManager(provider_capability=SimpleNamespace(runtime_kind="remote_pty"))

    assert type(manager.strategy).__name__ == "IncrementalSyncStrategy"
    assert captured["repo"] is None
