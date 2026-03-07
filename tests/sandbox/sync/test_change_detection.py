def test_detect_changed_files():
    from sandbox.sync.state import SyncState
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()

        state = SyncState()

        # Create file and track it
        file1 = workspace / "file1.txt"
        file1.write_text("content1")
        state.track_file("thread1", "file1.txt", "hash1", 1000)

        # Modify file
        file1.write_text("content2")

        # Detect changes
        changed = state.detect_changes("thread1", workspace)
        assert "file1.txt" in changed
