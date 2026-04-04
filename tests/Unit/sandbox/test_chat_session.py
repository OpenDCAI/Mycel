"""Unit tests for ChatSession and ChatSessionManager."""

import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from sandbox.chat_session import (
    ChatSession,
    ChatSessionManager,
    ChatSessionPolicy,
)
from sandbox.lease import lease_from_row
from sandbox.terminal import terminal_from_row
from storage.providers.sqlite.lease_repo import SQLiteLeaseRepo
from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo


@pytest.fixture
def terminal_store(temp_db):
    """Create SQLiteTerminalRepo with temp database."""
    store = SQLiteTerminalRepo(db_path=temp_db)
    yield store
    store.close()


class _LeaseStoreCompat:
    """Thin wrapper: repo returns dicts, tests expect domain objects from create/get."""

    def __init__(self, repo: SQLiteLeaseRepo):
        self._repo = repo

    def create(self, lease_id, provider_name, **kw):
        row = self._repo.create(lease_id, provider_name, **kw)
        return lease_from_row(row, self._repo.db_path)

    def get(self, lease_id):
        row = self._repo.get(lease_id)
        return lease_from_row(row, self._repo.db_path) if row else None

    def __getattr__(self, name):
        return getattr(self._repo, name)


@pytest.fixture
def lease_store(temp_db):
    """Create SQLiteLeaseRepo with compat wrapper for tests."""
    repo = SQLiteLeaseRepo(db_path=temp_db)
    compat = _LeaseStoreCompat(repo)
    yield compat
    repo.close()


@pytest.fixture
def mock_provider():
    """Create mock SandboxProvider."""
    from sandbox.providers.local import LocalPersistentShellRuntime

    provider = MagicMock()
    provider.name = "local"
    provider.create_runtime.side_effect = lambda terminal, lease: LocalPersistentShellRuntime(terminal, lease)
    return provider


@pytest.fixture
def session_manager(temp_db, mock_provider):
    """Create ChatSessionManager with temp database."""
    manager = ChatSessionManager(provider=mock_provider, db_path=temp_db)
    yield manager
    manager._repo.close()


class TestChatSessionPolicy:
    """Test ChatSessionPolicy dataclass."""

    def test_default_policy(self):
        """Test default policy values."""
        policy = ChatSessionPolicy()
        assert policy.idle_ttl_sec == 600
        assert policy.max_duration_sec == 86400

    def test_custom_policy(self):
        """Test custom policy values."""
        policy = ChatSessionPolicy(
            idle_ttl_sec=1800,
            max_duration_sec=43200,
        )
        assert policy.idle_ttl_sec == 1800
        assert policy.max_duration_sec == 43200


class TestChatSession:
    """Test ChatSession lifecycle."""

    def test_is_expired_idle_timeout(self, terminal_store, lease_store):
        """Test session expires after idle timeout."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")
        runtime = MagicMock()

        policy = ChatSessionPolicy(idle_ttl_sec=1, max_duration_sec=3600)
        now = datetime.now()

        session = ChatSession(
            session_id="sess-1",
            thread_id="thread-1",
            terminal=terminal,
            lease=lease,
            runtime=runtime,
            policy=policy,
            started_at=now,
            last_active_at=now - timedelta(seconds=2),  # 2 seconds ago
        )

        assert session.is_expired()

    def test_is_expired_max_duration(self, terminal_store, lease_store):
        """Test session expires after max duration."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")
        runtime = MagicMock()

        policy = ChatSessionPolicy(idle_ttl_sec=3600, max_duration_sec=1)
        now = datetime.now()

        session = ChatSession(
            session_id="sess-1",
            thread_id="thread-1",
            terminal=terminal,
            lease=lease,
            runtime=runtime,
            policy=policy,
            started_at=now - timedelta(seconds=2),  # Created 2 seconds ago
            last_active_at=now,
        )

        assert session.is_expired()

    def test_not_expired(self, terminal_store, lease_store):
        """Test session not expired when within limits."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")
        runtime = MagicMock()

        policy = ChatSessionPolicy(idle_ttl_sec=3600, max_duration_sec=86400)
        now = datetime.now()

        session = ChatSession(
            session_id="sess-1",
            thread_id="thread-1",
            terminal=terminal,
            lease=lease,
            runtime=runtime,
            policy=policy,
            started_at=now,
            last_active_at=now,
        )

        assert not session.is_expired()

    def test_touch_updates_activity(self, terminal_store, lease_store, session_manager, temp_db):
        """Test touch updates last_active_at."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")
        runtime = MagicMock()

        policy = ChatSessionPolicy()
        now = datetime.now()
        old_time = now - timedelta(seconds=10)

        session = ChatSession(
            session_id="sess-1",
            thread_id="thread-1",
            terminal=terminal,
            lease=lease,
            runtime=runtime,
            policy=policy,
            started_at=now,
            last_active_at=old_time,
            db_path=temp_db,
        )

        session.touch()

        # last_active_at should be updated
        assert session.last_active_at > old_time

    @pytest.mark.asyncio
    async def test_close_calls_runtime_close(self, terminal_store, lease_store, session_manager, temp_db):
        """Test close calls runtime.close()."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")
        runtime = MagicMock()
        runtime.close = MagicMock(return_value=asyncio.Future())
        runtime.close.return_value.set_result(None)

        policy = ChatSessionPolicy()
        now = datetime.now()

        session = ChatSession(
            session_id="sess-1",
            thread_id="thread-1",
            terminal=terminal,
            lease=lease,
            runtime=runtime,
            policy=policy,
            started_at=now,
            last_active_at=now,
            db_path=temp_db,
        )

        await session.close()

        runtime.close.assert_called_once()


class TestChatSessionManager:
    """Test ChatSessionManager CRUD operations."""

    def test_ensure_tables(self, session_manager, temp_db):
        """Test table creation."""

        # Verify table exists
        import sqlite3

        conn = sqlite3.connect(str(temp_db))
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_sessions'")
            assert cursor.fetchone() is not None
        finally:
            conn.close()

    def test_create_session(self, session_manager, terminal_store, lease_store):
        """Test creating a new session."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")

        session = session_manager.create(
            session_id="sess-1",
            thread_id="thread-1",
            terminal=terminal,
            lease=lease,
        )

        assert session.session_id == "sess-1"
        assert session.thread_id == "thread-1"
        assert session.terminal == terminal
        assert session.lease == lease
        assert session.runtime is not None

    def test_get_session(self, session_manager, terminal_store, lease_store):
        """Test retrieving session by thread_id."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")

        session_manager.create(
            session_id="sess-1",
            thread_id="thread-1",
            terminal=terminal,
            lease=lease,
        )

        session = session_manager.get("thread-1", "term-1")
        assert session is not None
        assert session.session_id == "sess-1"
        assert session.thread_id == "thread-1"

    def test_get_nonexistent_session(self, session_manager):
        """Test retrieving non-existent session returns None."""
        session = session_manager.get("nonexistent-thread", "nonexistent-term")
        assert session is None

    def test_get_expired_session_returns_none(self, session_manager, terminal_store, lease_store):
        """Test that expired session returns None and is cleaned up."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")

        # Create session with very short timeout
        policy = ChatSessionPolicy(idle_ttl_sec=0, max_duration_sec=86400)
        session_manager.create(
            session_id="sess-1",
            thread_id="thread-1",
            terminal=terminal,
            lease=lease,
            policy=policy,
        )

        time.sleep(0.1)  # Wait for expiry

        # Should return None and clean up
        session = session_manager.get("thread-1", "term-1")
        assert session is None

    def test_touch_updates_db(self, session_manager, terminal_store, lease_store, temp_db):
        """Test that touch updates database."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")

        session = session_manager.create(
            session_id="sess-1",
            thread_id="thread-1",
            terminal=terminal,
            lease=lease,
        )

        old_activity = session.last_active_at
        time.sleep(0.01)

        session_manager.touch("sess-1")

        # Retrieve again and verify updated
        session2 = session_manager.get("thread-1", "term-1")
        assert session2.last_active_at > old_activity

    def test_delete_session(self, session_manager, terminal_store, lease_store):
        """Test deleting a session."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")

        session_manager.create(
            session_id="sess-1",
            thread_id="thread-1",
            terminal=terminal,
            lease=lease,
        )

        # Verify exists
        assert session_manager.get("thread-1", "term-1") is not None

        # Delete
        session_manager.delete("sess-1")

        # Verify deleted
        assert session_manager.get("thread-1", "term-1") is None

    def test_list_all_sessions(self, session_manager, terminal_store, lease_store):
        """Test listing all sessions."""
        terminal1 = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1"), terminal_store.db_path)
        terminal2 = terminal_from_row(terminal_store.create("term-2", "thread-2", "lease-1"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")

        time.sleep(0.01)
        session_manager.create("sess-1", "thread-1", terminal1, lease)
        time.sleep(0.01)
        session_manager.create("sess-2", "thread-2", terminal2, lease)

        sessions = session_manager.list_all()
        assert len(sessions) == 2

        # Should be ordered by created_at DESC
        assert sessions[0]["session_id"] == "sess-2"
        assert sessions[1]["session_id"] == "sess-1"

    def test_cleanup_expired(self, session_manager, terminal_store, lease_store):
        """Test cleanup_expired removes expired sessions."""
        terminal1 = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1"), terminal_store.db_path)
        terminal2 = terminal_from_row(terminal_store.create("term-2", "thread-2", "lease-1"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")

        # Create one expired session
        policy_expired = ChatSessionPolicy(idle_ttl_sec=0, max_duration_sec=86400)
        session_manager.create("sess-1", "thread-1", terminal1, lease, policy=policy_expired)

        # Create one active session
        policy_active = ChatSessionPolicy(idle_ttl_sec=3600, max_duration_sec=86400)
        session_manager.create("sess-2", "thread-2", terminal2, lease, policy=policy_active)

        time.sleep(0.1)  # Wait for expiry

        # Cleanup
        count = session_manager.cleanup_expired()

        assert count == 1
        assert session_manager.get("thread-1", "term-1") is None
        assert session_manager.get("thread-2", "term-2") is not None


class TestChatSessionIntegration:
    """Integration tests for chat session lifecycle."""

    def test_full_lifecycle(self, session_manager, terminal_store, lease_store):
        """Test complete session lifecycle: create → use → expire → cleanup."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")

        # Create session
        session = session_manager.create("sess-1", "thread-1", terminal, lease)
        assert session is not None

        # Touch to update activity
        session_manager.touch("sess-1")

        # Retrieve again
        session2 = session_manager.get("thread-1", "term-1")
        assert session2 is not None

        # Delete
        session_manager.delete("sess-1")
        assert session_manager.get("thread-1", "term-1") is None

    def test_session_with_custom_policy(self, session_manager, terminal_store, lease_store):
        """Test session with custom policy."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")

        policy = ChatSessionPolicy(idle_ttl_sec=1800, max_duration_sec=43200)
        session = session_manager.create("sess-1", "thread-1", terminal, lease, policy=policy)

        assert session.policy.idle_ttl_sec == 1800
        assert session.policy.max_duration_sec == 43200
