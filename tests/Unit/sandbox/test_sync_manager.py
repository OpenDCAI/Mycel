from types import SimpleNamespace

import pytest

import sandbox.sync.manager as sync_manager_module


def test_sync_manager_uses_process_local_backing_for_remote_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_build_sync_file_repo():
        raise AssertionError("persisted sync_file repo should stay unused for remote runtime first cut")

    monkeypatch.setattr(sync_manager_module, "build_sync_file_repo", fail_build_sync_file_repo, raising=False)

    manager = sync_manager_module.SyncManager(provider_capability=SimpleNamespace(runtime_kind="remote_pty"))

    assert type(manager.strategy).__name__ == "IncrementalSyncStrategy"
