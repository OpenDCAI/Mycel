from sandbox.sync.state import ProcessLocalSyncFileBacking, SyncState


def test_process_local_sync_backing_exposes_only_batch_list_and_clear() -> None:
    backing = ProcessLocalSyncFileBacking()

    assert hasattr(backing, "track_files_batch")
    assert hasattr(backing, "get_all_files")
    assert hasattr(backing, "clear_thread")
    assert not hasattr(backing, "track_file")
    assert not hasattr(backing, "get_file_info")


def test_sync_state_exposes_only_batch_list_and_clear_protocol() -> None:
    state = SyncState(repo=ProcessLocalSyncFileBacking())

    assert hasattr(state, "track_files_batch")
    assert hasattr(state, "get_all_files")
    assert hasattr(state, "clear_thread")
    assert not hasattr(state, "track_file")
    assert not hasattr(state, "get_file_info")


def test_sync_state_defaults_to_process_local_backing() -> None:
    state = SyncState()

    assert isinstance(state._repo, ProcessLocalSyncFileBacking)
