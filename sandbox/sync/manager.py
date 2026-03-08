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
        return IncrementalSyncStrategy(self.workspace_root, state, self)

    def get_thread_workspace_path(self, thread_id: str) -> Path:
        """Get the local workspace path for a thread, respecting workspace sharing."""
        from backend.web.utils.helpers import load_thread_config, _get_container

        tc = load_thread_config(thread_id)
        if tc and tc.workspace_id:
            # Thread uses shared workspace
            repo = _get_container().workspace_repo()
            try:
                ws = repo.get(tc.workspace_id)
                if ws:
                    return Path(ws["host_path"]).resolve()
            finally:
                repo.close()
        # Default per-thread path
        return self.workspace_root / thread_id / "files"

    def upload_workspace(self, thread_id: str, session_id: str, provider, files: list[str] | None = None):
        """Upload workspace files to sandbox."""
        self.strategy.upload(thread_id, session_id, provider, files=files)

    def download_workspace(self, thread_id: str, session_id: str, provider):
        """Download workspace files from sandbox."""
        self.strategy.download(thread_id, session_id, provider)
