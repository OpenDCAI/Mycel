def test_sync_state_track_file():
    from sandbox.sync.state import SyncState

    state = SyncState()

    state.track_file("thread1", "file.txt", "abc123", 1234567890)

    info = state.get_file_info("thread1", "file.txt")
    assert info["checksum"] == "abc123"
    assert info["last_synced"] == 1234567890
