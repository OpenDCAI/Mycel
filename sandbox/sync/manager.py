from pathlib import Path
from sandbox.sync.strategy import SyncStrategy

class SyncManager:
    def __init__(self, provider_capability, workspace_root: Path):
        self.provider_capability = provider_capability
        self.workspace_root = workspace_root
        self.strategy = self._select_strategy()

    def _select_strategy(self) -> SyncStrategy:
        from sandbox.sync.strategy import NoOpStrategy, IncrementalSyncStrategy
        from sandbox.sync.state import SyncState

        runtime_kind = self.provider_capability.runtime_kind

        # Docker and local use bind mounts - no sync needed
        if runtime_kind in ("local", "docker"):
            return NoOpStrategy()

        # Remote providers use incremental sync
        state = SyncState()
        return IncrementalSyncStrategy(self.workspace_root, state)
