def test_select_strategy_for_docker():
    from sandbox.sync.manager import SyncManager
    from sandbox.sync.strategy import NoOpStrategy
    from pathlib import Path

    class MockCapability:
        runtime_kind = "docker"

    capability = MockCapability()
    manager = SyncManager(capability, Path("/tmp"))

    assert isinstance(manager.strategy, NoOpStrategy)

def test_select_strategy_for_daytona():
    from sandbox.sync.manager import SyncManager
    from sandbox.sync.strategy import IncrementalSyncStrategy
    from pathlib import Path

    class MockCapability:
        runtime_kind = "daytona"

    capability = MockCapability()
    manager = SyncManager(capability, Path("/tmp"))

    assert isinstance(manager.strategy, IncrementalSyncStrategy)
