from sandbox.sync.state import ProcessLocalSyncFileBacking


def test_process_local_sync_backing_exposes_only_batch_list_and_clear() -> None:
    backing = ProcessLocalSyncFileBacking()

    assert hasattr(backing, "track_files_batch")
    assert hasattr(backing, "get_all_files")
    assert hasattr(backing, "clear_thread")
    assert not hasattr(backing, "track_file")
    assert not hasattr(backing, "get_file_info")
