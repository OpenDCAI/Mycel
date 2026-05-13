from sandbox.sync.state import InMemorySyncFileBacking, SyncState


def test_sync_state_defaults_to_memory_backing() -> None:
    state = SyncState()

    assert isinstance(state._repo, InMemorySyncFileBacking)
