from pathlib import Path
import pytest
from sandbox.sync.state import SyncState, _calculate_checksum
from sandbox.sync.strategy import IncrementalSyncStrategy


@pytest.fixture
def sync_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LEON_SANDBOX_DB_PATH", str(tmp_path / "sandbox.db"))
    state = SyncState()
    strategy = IncrementalSyncStrategy(workspace_root=tmp_path, state=state)
    workspace = tmp_path / "thread-1" / "files"
    workspace.mkdir(parents=True)
    return state, strategy, workspace


def test_download_updates_checksums(sync_env):
    """After download, checksums should reflect downloaded files so next upload doesn't redundantly re-upload."""
    state, strategy, workspace = sync_env

    # Simulate: file was uploaded (tracked in DB with checksum A)
    (workspace / "readme.txt").write_text("original")
    original_checksum = _calculate_checksum(workspace / "readme.txt")
    state.track_file("thread-1", "readme.txt", original_checksum, 1000)

    # Simulate: agent modified file in sandbox, then downloaded (overwritten locally)
    (workspace / "readme.txt").write_text("agent-modified")
    new_checksum = _calculate_checksum(workspace / "readme.txt")

    # After download, checksums should be updated
    strategy._update_checksums_after_download("thread-1")

    # Verify DB has new checksum
    info = state.get_file_info("thread-1", "readme.txt")
    assert info["checksum"] == new_checksum

    # detect_changes should return empty (nothing to upload)
    changes = state.detect_changes("thread-1", workspace)
    assert changes == []
