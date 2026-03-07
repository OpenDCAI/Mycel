def test_full_sync_upload():
    from sandbox.sync.strategy import FullSyncStrategy
    from pathlib import Path
    import tempfile

    class MockProvider:
        def __init__(self):
            self.uploaded = {}

        def write_file(self, session_id, remote_path, content):
            self.uploaded[remote_path] = content

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_root = Path(tmpdir)
        files_dir = workspace_root / "thread1" / "files"
        files_dir.mkdir(parents=True)
        (files_dir / "file1.txt").write_text("content1")
        (files_dir / "file2.txt").write_text("content2")

        provider = MockProvider()
        strategy = FullSyncStrategy(workspace_root)

        strategy.upload("thread1", "session1", provider)

        assert len(provider.uploaded) == 2
        assert "/workspace/files/file1.txt" in provider.uploaded
