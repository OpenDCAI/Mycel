from types import SimpleNamespace

import sandbox.sync.manager as sync_manager_module


def test_sync_manager_uses_process_local_backing_for_remote_runtime() -> None:
    manager = sync_manager_module.SyncManager(provider_capability=SimpleNamespace(runtime_kind="remote_pty"))

    assert type(manager.strategy).__name__ == "IncrementalSyncStrategy"
