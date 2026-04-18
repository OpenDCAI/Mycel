from sandbox.sync.state import ProcessLocalSyncFileBacking, SyncState


def test_sync_state_defaults_to_process_local_backing() -> None:
    state = SyncState()

    assert isinstance(state._repo, ProcessLocalSyncFileBacking)
