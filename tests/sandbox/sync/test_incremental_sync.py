def test_incremental_sync_only_changed():
    from sandbox.sync.strategy import IncrementalSyncStrategy
    from sandbox.sync.state import SyncState
    from pathlib import Path
    import tempfile

    class MockProvider:
        def __init__(self):
            self.uploaded = []

        def write_file(self, session_id, remote_path, content):
            self.uploaded.append(remote_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_root = Path(tmpdir)
        files_dir = workspace_root / "thread1" / "files"
        files_dir.mkdir(parents=True)

        state = SyncState()
        provider = MockProvider()
        strategy = IncrementalSyncStrategy(workspace_root, state)

        # First sync
        (files_dir / "file1.txt").write_text("content1")
        strategy.upload("thread1", "session1", provider)
        assert len(provider.uploaded) == 1

        # Second sync - no changes
        provider.uploaded.clear()
        strategy.upload("thread1", "session1", provider)
        assert len(provider.uploaded) == 0
