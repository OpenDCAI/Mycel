from pathlib import Path

from sandbox.sync.strategy import SyncStrategy


class SyncManager:
    def __init__(self, provider_capability):
        self.provider_capability = provider_capability
        self.strategy = self._select_strategy()

    def _select_strategy(self) -> SyncStrategy:
        from sandbox.sync.state import ProcessLocalSyncFileBacking, SyncState
        from sandbox.sync.strategy import IncrementalSyncStrategy, NoOpStrategy

        runtime_kind = self.provider_capability.runtime_kind
        if runtime_kind in ("local", "docker_pty"):
            return NoOpStrategy()
        # @@@sync-process-local-first-cut - remote runtimes now get a process-local checksum backing
        # so incremental sync no longer defaults to a persisted sync_files repo on the first cut.
        state = SyncState(repo=ProcessLocalSyncFileBacking())
        return IncrementalSyncStrategy(state)

    def upload(
        self,
        source_path: Path,
        remote_path: str,
        session_id: str,
        provider,
        files: list[str] | None = None,
        state_key: str | None = None,
    ):
        self.strategy.upload(source_path, remote_path, session_id, provider, files=files, state_key=state_key)

    def download(self, source_path: Path, remote_path: str, session_id: str, provider, state_key: str | None = None):
        self.strategy.download(source_path, remote_path, session_id, provider, state_key=state_key)

    def clear_state(self, state_key: str):
        self.strategy.clear_state(state_key)
