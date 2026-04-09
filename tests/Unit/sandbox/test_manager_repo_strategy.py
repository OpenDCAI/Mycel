from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from sandbox.chat_session import ChatSession, ChatSessionPolicy
from sandbox.lease import SandboxLease
from sandbox.manager import (
    bind_thread_to_existing_lease,
    bind_thread_to_existing_thread_lease,
    lookup_sandbox_for_thread,
    resolve_existing_lease_cwd,
)
from sandbox.terminal import AbstractTerminal, TerminalState


def test_sandbox_manager_no_longer_imports_storage_factory() -> None:
    manager_source = Path("sandbox/manager.py").read_text(encoding="utf-8")

    assert "backend.web.core.storage_factory" not in manager_source
    assert "sandbox.control_plane_repos" in manager_source
    assert "SQLiteTerminalRepo" not in manager_source
    assert "SQLiteLeaseRepo" not in manager_source
    assert "SQLiteChatSessionRepo" not in manager_source


def test_chat_session_manager_uses_control_plane_repo_seam() -> None:
    session_source = Path("sandbox/chat_session.py").read_text(encoding="utf-8")

    assert "sandbox.control_plane_repos" in session_source
    assert "SQLiteTerminalRepo" not in session_source
    assert "SQLiteLeaseRepo" not in session_source
    assert "SQLiteChatSessionRepo" not in session_source


class _FakeTerminalRepo:
    def __init__(self, *, by_thread=None, active_by_thread=None, latest_by_lease=None):
        self._by_thread = by_thread or {}
        self._active_by_thread = active_by_thread or {}
        self._latest_by_lease = latest_by_lease or {}
        self.created = []
        self.closed = False

    def list_by_thread(self, thread_id: str):
        return list(self._by_thread.get(thread_id, []))

    def get_active(self, thread_id: str):
        return self._active_by_thread.get(thread_id)

    def get_latest_by_lease(self, lease_id: str):
        return self._latest_by_lease.get(lease_id)

    def create(self, terminal_id: str, thread_id: str, lease_id: str, initial_cwd: str = "/root"):
        row = {
            "terminal_id": terminal_id,
            "thread_id": thread_id,
            "lease_id": lease_id,
            "cwd": initial_cwd,
        }
        self.created.append(row)
        self._active_by_thread[thread_id] = row
        return row

    def close(self):
        self.closed = True


class _FakeLeaseRepo:
    def __init__(self, leases=None):
        self._leases = leases or {}
        self.closed = False

    def get(self, lease_id: str):
        return self._leases.get(lease_id)

    def close(self):
        self.closed = True


class _FakeSessionRepo:
    def __init__(self):
        self.touches = []
        self.deletes = []

    def touch(self, session_id: str, last_active_at: str | None = None, status: str | None = None) -> None:
        self.touches.append((session_id, last_active_at, status))

    def delete_session(self, session_id: str, *, reason: str = "closed") -> None:
        self.deletes.append((session_id, reason))


class _RepoStub:
    def close(self):
        return None


class _ActiveTerminalRepoStub(_RepoStub):
    def get_active(self, _thread_id: str):
        return {"terminal_id": "term-1", "lease_id": "lease-1", "cwd": "/workspace"}

    def list_by_thread(self, _thread_id: str):
        return [{"terminal_id": "term-1", "lease_id": "lease-1", "cwd": "/workspace"}]


class _LeaseRowRepoStub(_RepoStub):
    def get(self, _lease_id: str):
        return {"lease_id": "lease-1", "provider_name": "daytona_selfhost"}


class _FakeTerminal(AbstractTerminal):
    def __init__(self):
        super().__init__("term-1", "thread-1", "lease-1", TerminalState(cwd="/workspace"))

    def _persist_state(self) -> None:
        raise AssertionError("terminal persistence should not run in this test")


class _FakeLease(SandboxLease):
    def __init__(self):
        super().__init__(lease_id="lease-1", provider_name="local")

    def ensure_active_instance(self, provider):
        raise AssertionError("not used")

    def destroy_instance(self, provider, *, source: str = "api") -> None:
        raise AssertionError("not used")

    def pause_instance(self, provider, *, source: str = "api") -> bool:
        raise AssertionError("not used")

    def resume_instance(self, provider, *, source: str = "api") -> bool:
        raise AssertionError("not used")

    def refresh_instance_status(self, provider, *, force: bool = False, max_age_sec: float = 3.0) -> str:
        raise AssertionError("not used")

    def mark_needs_refresh(self, hint_at=None) -> None:
        raise AssertionError("not used")

    def apply(self, provider, *, event_type: str, source: str, payload=None, event_id=None) -> dict:
        raise AssertionError("not used")


def test_lookup_sandbox_for_thread_accepts_injected_repos():
    terminal_repo = _FakeTerminalRepo(
        by_thread={"thread-1": [{"terminal_id": "term-1", "lease_id": "lease-1"}]},
    )
    lease_repo = _FakeLeaseRepo(leases={"lease-1": {"provider_name": "daytona"}})

    provider_name = lookup_sandbox_for_thread("thread-1", terminal_repo=terminal_repo, lease_repo=lease_repo)

    assert provider_name == "daytona"
    assert terminal_repo.closed is False
    assert lease_repo.closed is False


def test_bind_thread_to_existing_lease_accepts_injected_terminal_repo():
    terminal_repo = _FakeTerminalRepo(
        latest_by_lease={"lease-1": {"cwd": "/workspace/project"}},
    )

    cwd = bind_thread_to_existing_lease("thread-2", "lease-1", terminal_repo=terminal_repo)

    assert cwd == "/workspace/project"
    assert terminal_repo.created[0]["thread_id"] == "thread-2"
    assert terminal_repo.created[0]["lease_id"] == "lease-1"
    assert terminal_repo.created[0]["cwd"] == "/workspace/project"


def test_bind_thread_to_existing_thread_lease_accepts_injected_terminal_repo():
    terminal_repo = _FakeTerminalRepo(
        active_by_thread={"thread-parent": {"terminal_id": "term-parent", "lease_id": "lease-1", "cwd": "/workspace"}},
        latest_by_lease={"lease-1": {"cwd": "/workspace"}},
    )

    cwd = bind_thread_to_existing_thread_lease("thread-child", "thread-parent", terminal_repo=terminal_repo)

    assert cwd == "/workspace"
    assert terminal_repo.created[0]["thread_id"] == "thread-child"
    assert terminal_repo.created[0]["lease_id"] == "lease-1"


def test_resolve_existing_lease_cwd_accepts_injected_terminal_repo():
    terminal_repo = _FakeTerminalRepo(latest_by_lease={"lease-1": {"cwd": "/tmp/worktree"}})

    cwd = resolve_existing_lease_cwd("lease-1", terminal_repo=terminal_repo)

    assert cwd == "/tmp/worktree"


def test_chat_session_touch_uses_injected_repo():
    repo = _FakeSessionRepo()
    session = ChatSession(
        session_id="sess-1",
        thread_id="thread-1",
        terminal=_FakeTerminal(),
        lease=_FakeLease(),
        runtime=object(),
        policy=ChatSessionPolicy(),
        started_at=__import__("datetime").datetime.now(),
        last_active_at=__import__("datetime").datetime.now(),
        session_repo=repo,
    )

    session.touch()

    assert repo.touches
    assert repo.touches[0][0] == "sess-1"
    assert repo.touches[0][2] == "active"


def test_chat_session_close_uses_injected_repo():
    class _Runtime:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True

    repo = _FakeSessionRepo()
    runtime = _Runtime()
    session = ChatSession(
        session_id="sess-1",
        thread_id="thread-1",
        terminal=_FakeTerminal(),
        lease=_FakeLease(),
        runtime=runtime,
        policy=ChatSessionPolicy(),
        started_at=__import__("datetime").datetime.now(),
        last_active_at=__import__("datetime").datetime.now(),
        session_repo=repo,
    )

    import asyncio

    asyncio.run(session.close(reason="closed"))

    assert runtime.closed is True
    assert repo.deletes == [("sess-1", "closed")]


def test_chat_session_is_expired_accepts_aware_supabase_timestamps():
    aware = datetime.fromisoformat("2099-04-08T00:00:00+00:00")
    session = ChatSession(
        session_id="sess-1",
        thread_id="thread-1",
        terminal=_FakeTerminal(),
        lease=_FakeLease(),
        runtime=object(),
        policy=ChatSessionPolicy(),
        started_at=aware,
        last_active_at=aware,
        session_repo=_FakeSessionRepo(),
    )

    assert session.is_expired() is False


def test_sandbox_manager_keeps_sandbox_repos_sqlite_owned_under_supabase(monkeypatch):
    import sandbox.manager as sandbox_manager_module

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr(sandbox_manager_module, "make_terminal_repo", lambda db_path=None: _RepoStub())
    monkeypatch.setattr(sandbox_manager_module, "make_lease_repo", lambda db_path=None: _RepoStub())
    monkeypatch.setattr(sandbox_manager_module, "make_chat_session_repo", lambda db_path=None: _RepoStub(), raising=False)

    provider = SimpleNamespace(get_capability=lambda: SimpleNamespace(runtime_kind="local"))

    manager = sandbox_manager_module.SandboxManager(provider=provider)

    assert isinstance(manager.terminal_store, _RepoStub)
    assert isinstance(manager.lease_store, _RepoStub)


def test_sandbox_manager_uses_own_db_path_when_repo_has_no_db_path(monkeypatch, tmp_path):
    import sandbox.manager as sandbox_manager_module

    manager = object.__new__(sandbox_manager_module.SandboxManager)
    manager.db_path = tmp_path / "sandbox.db"
    manager.terminal_store = _ActiveTerminalRepoStub()
    manager.lease_store = _LeaseRowRepoStub()

    seen_terminal_db_paths = []
    seen_lease_db_paths = []
    monkeypatch.setattr(
        sandbox_manager_module,
        "terminal_from_row",
        lambda row, db_path: seen_terminal_db_paths.append(db_path) or row,
    )
    monkeypatch.setattr(
        sandbox_manager_module,
        "lease_from_row",
        lambda row, db_path: seen_lease_db_paths.append(db_path) or row,
    )

    terminal = manager._get_active_terminal("thread-1")
    lease = manager._get_lease("lease-1")

    assert terminal["terminal_id"] == "term-1"
    assert lease["lease_id"] == "lease-1"
    assert seen_terminal_db_paths == [manager.db_path]
    assert seen_lease_db_paths == [manager.db_path]
