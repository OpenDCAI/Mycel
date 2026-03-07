from pathlib import Path
from sandbox.sync.strategy import SyncStrategy

class SyncManager:
    def __init__(self, provider_capability, workspace_root: Path):
        self.provider_capability = provider_capability
        self.workspace_root = workspace_root
        self.strategy = self._select_strategy()

    def _select_strategy(self) -> SyncStrategy:
        from sandbox.sync.strategy import NoOpStrategy
        return NoOpStrategy()
