def test_sync_manager_initialization():
    from sandbox.sync.manager import SyncManager
    from pathlib import Path

    class MockCapability:
        runtime_kind = "docker"

    capability = MockCapability()
    manager = SyncManager(capability, Path("/tmp"))

    assert manager.provider_capability == capability
    assert manager.workspace_root == Path("/tmp")
    assert manager.strategy is not None
