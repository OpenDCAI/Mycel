def test_e2e_file_upload_sync():
    from sandbox.sync.manager import SyncManager
    from pathlib import Path
    import tempfile
    import uuid

    class MockCapability:
        runtime_kind = "daytona"

    class MockProvider:
        def __init__(self):
            self.uploaded = {}

        def write_file(self, session_id, remote_path, content):
            self.uploaded[remote_path] = content

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_root = Path(tmpdir)
        capability = MockCapability()
        manager = SyncManager(capability, workspace_root)

        # Simulate file upload with unique thread_id
        thread_id = f"test-{uuid.uuid4().hex[:8]}"
        workspace = workspace_root / thread_id / "files"
        workspace.mkdir(parents=True)
        (workspace / "uploaded.txt").write_text("test content")

        # Mock provider
        provider = MockProvider()
        session_id = "test-session"

        # Upload single file
        manager.upload_workspace(thread_id, session_id, provider)

        # Verify file was uploaded
        assert "/workspace/files/uploaded.txt" in provider.uploaded
        assert provider.uploaded["/workspace/files/uploaded.txt"] == "test content"
