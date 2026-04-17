from backend.web.utils import helpers


class _FakeContainer:
    def __init__(self) -> None:
        self.purged: list[str] = []

    def purge_thread(self, thread_id: str) -> None:
        self.purged.append(thread_id)


class _ThreadRepo:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.closed = False
        self.timestamps = ("created", "updated")
        self.lease = {"created_at": "lease-created", "updated_at": "lease-updated"}

    def delete_by_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)

    def get_timestamps(self, terminal_id: str) -> tuple[str, str]:
        assert terminal_id == "terminal-1"
        return self.timestamps

    def get(self, lease_id: str) -> dict[str, str]:
        assert lease_id == "lease-1"
        return self.lease

    def close(self) -> None:
        self.closed = True


class _SyncState:
    def __init__(self, repo=None) -> None:
        self.cleared: list[str] = []
        self.closed = False
        self.repo = repo

    def clear_thread(self, thread_id: str) -> int:
        self.cleared.append(thread_id)
        return 1

    def close(self) -> None:
        self.closed = True


def test_delete_thread_in_db_uses_runtime_repo_factories_without_db_path(monkeypatch, tmp_path):
    sandbox_db = tmp_path / "sandbox.db"
    sandbox_db.touch()
    container = _FakeContainer()
    session_repo = _ThreadRepo()
    terminal_repo = _ThreadRepo()
    sync_state_holder: dict[str, _SyncState] = {}

    monkeypatch.setattr(helpers, "_get_container", lambda: container)
    monkeypatch.setattr(helpers, "resolve_sandbox_db_path", lambda: sandbox_db)
    monkeypatch.setattr(helpers, "make_chat_session_repo", lambda: session_repo)
    monkeypatch.setattr(helpers, "make_terminal_repo", lambda: terminal_repo)
    monkeypatch.setattr(
        helpers,
        "SyncState",
        lambda **kwargs: sync_state_holder.setdefault("instance", _SyncState(**kwargs)),
    )

    helpers.delete_thread_in_db("thread-1")

    sync_state = sync_state_holder["instance"]
    assert container.purged == ["thread-1"]
    assert session_repo.deleted == ["thread-1"]
    assert terminal_repo.deleted == ["thread-1"]
    assert sync_state.cleared == ["thread-1"]
    assert session_repo.closed
    assert terminal_repo.closed
    assert sync_state.closed
    assert type(sync_state.repo).__name__ == "ProcessLocalSyncFileBacking"


def test_delete_thread_in_db_cleans_runtime_repos_when_supabase_defaults_without_local_db(monkeypatch, tmp_path):
    sandbox_db = tmp_path / "missing-sandbox.db"
    container = _FakeContainer()
    session_repo = _ThreadRepo()
    terminal_repo = _ThreadRepo()
    sync_state_holder: dict[str, _SyncState] = {}

    monkeypatch.setattr(helpers, "_get_container", lambda: container)
    monkeypatch.setattr(helpers, "resolve_sandbox_db_path", lambda: sandbox_db)
    monkeypatch.setattr(helpers, "uses_supabase_runtime_defaults", lambda: True)
    monkeypatch.setattr(helpers, "make_chat_session_repo", lambda: session_repo)
    monkeypatch.setattr(helpers, "make_terminal_repo", lambda: terminal_repo)
    monkeypatch.setattr(
        helpers,
        "SyncState",
        lambda **kwargs: sync_state_holder.setdefault("instance", _SyncState(**kwargs)),
    )

    helpers.delete_thread_in_db("thread-1")

    sync_state = sync_state_holder["instance"]
    assert container.purged == ["thread-1"]
    assert session_repo.deleted == ["thread-1"]
    assert terminal_repo.deleted == ["thread-1"]
    assert sync_state.cleared == ["thread-1"]
    assert session_repo.closed
    assert terminal_repo.closed
    assert sync_state.closed


def test_helpers_no_longer_expose_terminal_timestamp_helper() -> None:
    assert not hasattr(helpers, "get_terminal_timestamps")


def test_helpers_no_longer_expose_lease_timestamp_helper() -> None:
    assert not hasattr(helpers, "get_lease_timestamps")


def test_load_thread_row_returns_current_thread_row(monkeypatch) -> None:
    thread_repo = _ThreadRepo()
    thread_repo.row = {"id": "thread-1", "cwd": "/workspace"}
    thread_repo.requested_ids = []

    def get_by_id(thread_id: str):
        thread_repo.requested_ids.append(thread_id)
        return thread_repo.row

    thread_repo.get_by_id = get_by_id

    assert helpers.load_thread_row("thread-1", thread_repo=thread_repo) == {"id": "thread-1", "cwd": "/workspace"}
    assert thread_repo.requested_ids == ["thread-1"]
