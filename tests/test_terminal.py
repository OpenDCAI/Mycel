"""Unit tests for AbstractTerminal and TerminalStore."""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from sandbox.terminal import TerminalState, terminal_from_row
from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    db_path.unlink(missing_ok=True)


@pytest.fixture
def store(temp_db):
    """Create SQLiteTerminalRepo with temp database."""
    return SQLiteTerminalRepo(db_path=temp_db)


def _wrap(store, row):
    """Wrap a repo dict into an AbstractTerminal domain object."""
    if row is None:
        return None
    return terminal_from_row(row, store.db_path)


class TestTerminalState:
    """Test TerminalState dataclass."""

    def test_create_default(self):
        """Test creating TerminalState with defaults."""
        state = TerminalState(cwd="/home/user")
        assert state.cwd == "/home/user"
        assert state.env_delta == {}
        assert state.state_version == 0

    def test_create_with_env(self):
        """Test creating TerminalState with env_delta."""
        state = TerminalState(
            cwd="/home/user",
            env_delta={"FOO": "bar", "BAZ": "qux"},
            state_version=5,
        )
        assert state.cwd == "/home/user"
        assert state.env_delta == {"FOO": "bar", "BAZ": "qux"}
        assert state.state_version == 5

    def test_to_json(self):
        """Test serialization to JSON."""
        state = TerminalState(
            cwd="/home/user",
            env_delta={"FOO": "bar"},
            state_version=3,
        )
        json_str = state.to_json()
        data = json.loads(json_str)

        assert data["cwd"] == "/home/user"
        assert data["env_delta"] == {"FOO": "bar"}
        assert data["state_version"] == 3

    def test_from_json(self):
        """Test deserialization from JSON."""
        json_str = json.dumps(
            {
                "cwd": "/home/user",
                "env_delta": {"FOO": "bar"},
                "state_version": 3,
            }
        )
        state = TerminalState.from_json(json_str)

        assert state.cwd == "/home/user"
        assert state.env_delta == {"FOO": "bar"}
        assert state.state_version == 3

    def test_from_json_missing_fields(self):
        """Test deserialization with missing optional fields."""
        json_str = json.dumps({"cwd": "/home/user"})
        state = TerminalState.from_json(json_str)

        assert state.cwd == "/home/user"
        assert state.env_delta == {}
        assert state.state_version == 0


class TestTerminalStore:
    """Test SQLiteTerminalRepo CRUD operations."""

    def test_ensure_tables(self, temp_db):
        """Test table creation."""
        _store = SQLiteTerminalRepo(db_path=temp_db)

        # Verify table exists
        with sqlite3.connect(str(temp_db)) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='abstract_terminals'")
            assert cursor.fetchone() is not None

    def test_create_terminal(self, store):
        """Test creating a new terminal."""
        terminal = _wrap(
            store,
            store.create(
                terminal_id="term-123",
                thread_id="thread-456",
                lease_id="lease-789",
                initial_cwd="/home/user",
            ),
        )

        assert terminal.terminal_id == "term-123"
        assert terminal.thread_id == "thread-456"
        assert terminal.lease_id == "lease-789"
        assert terminal.get_state().cwd == "/home/user"
        assert terminal.get_state().env_delta == {}
        assert terminal.get_state().state_version == 0

    def test_get_terminal_by_thread_id(self, store):
        """Test retrieving terminal by thread_id."""
        store.create(
            terminal_id="term-123",
            thread_id="thread-456",
            lease_id="lease-789",
            initial_cwd="/home/user",
        )

        terminal = _wrap(store, store.get_active("thread-456"))
        assert terminal is not None
        assert terminal.terminal_id == "term-123"
        assert terminal.thread_id == "thread-456"
        assert terminal.lease_id == "lease-789"

    def test_get_terminal_by_id(self, store):
        """Test retrieving terminal by terminal_id."""
        store.create(
            terminal_id="term-123",
            thread_id="thread-456",
            lease_id="lease-789",
            initial_cwd="/home/user",
        )

        terminal = _wrap(store, store.get_by_id("term-123"))
        assert terminal is not None
        assert terminal.terminal_id == "term-123"
        assert terminal.thread_id == "thread-456"

    def test_get_nonexistent_terminal(self, store):
        """Test retrieving non-existent terminal returns None."""
        terminal = store.get_active("nonexistent-thread")
        assert terminal is None

        terminal = store.get_by_id("nonexistent-terminal")
        assert terminal is None

    def test_delete_terminal(self, store):
        """Test deleting a terminal."""
        store.create(
            terminal_id="term-123",
            thread_id="thread-456",
            lease_id="lease-789",
        )

        # Verify exists
        assert store.get_active("thread-456") is not None

        # Delete
        store.delete("term-123")

        # Verify deleted
        assert store.get_active("thread-456") is None

    def test_delete_terminal_cleans_command_chunks(self, store, temp_db):
        """Deleting a terminal should remove command rows and associated output chunks."""
        store.create(
            terminal_id="term-123",
            thread_id="thread-456",
            lease_id="lease-789",
        )
        with sqlite3.connect(str(temp_db)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS terminal_commands (
                    command_id TEXT PRIMARY KEY,
                    terminal_id TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS terminal_command_chunks (
                    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    command_id TEXT NOT NULL,
                    stream TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO terminal_commands (command_id, terminal_id) VALUES (?, ?)",
                ("cmd-1", "term-123"),
            )
            conn.execute(
                """
                INSERT INTO terminal_command_chunks (command_id, stream, content, created_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                ("cmd-1", "stdout", "line-1"),
            )
            conn.commit()

        store.delete("term-123")

        with sqlite3.connect(str(temp_db)) as conn:
            cmd_row = conn.execute("SELECT command_id FROM terminal_commands WHERE command_id = ?", ("cmd-1",)).fetchone()
            chunk_row = conn.execute(
                "SELECT chunk_id FROM terminal_command_chunks WHERE command_id = ?",
                ("cmd-1",),
            ).fetchone()
        assert cmd_row is None
        assert chunk_row is None

    def test_list_all_terminals(self, store):
        """Test listing all terminals."""
        import time

        store.create("term-1", "thread-1", "lease-1", "/home/user1")
        time.sleep(0.01)  # Ensure different timestamps
        store.create("term-2", "thread-2", "lease-1", "/home/user2")
        time.sleep(0.01)
        store.create("term-3", "thread-3", "lease-2", "/home/user3")

        terminals = store.list_all()
        assert len(terminals) == 3

        # Should be ordered by created_at DESC
        assert terminals[0]["terminal_id"] == "term-3"
        assert terminals[1]["terminal_id"] == "term-2"
        assert terminals[2]["terminal_id"] == "term-1"


class TestSQLiteTerminal:
    """Test SQLiteTerminal state persistence."""

    def test_update_state_increments_version(self, store):
        """Test that update_state increments state_version."""
        terminal = _wrap(store, store.create("term-1", "thread-1", "lease-1", "/home/user"))

        assert terminal.get_state().state_version == 0

        # Update state
        new_state = TerminalState(cwd="/home/user/project", env_delta={"FOO": "bar"})
        terminal.update_state(new_state)

        assert terminal.get_state().state_version == 1
        assert terminal.get_state().cwd == "/home/user/project"
        assert terminal.get_state().env_delta == {"FOO": "bar"}

    def test_update_state_persists_to_db(self, store, temp_db):
        """Test that update_state persists to database."""
        terminal = _wrap(store, store.create("term-1", "thread-1", "lease-1", "/home/user"))

        # Update state
        new_state = TerminalState(
            cwd="/home/user/project",
            env_delta={"FOO": "bar", "BAZ": "qux"},
        )
        terminal.update_state(new_state)

        # Verify persisted to DB
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT cwd, env_delta_json, state_version FROM abstract_terminals WHERE terminal_id = ?",
                ("term-1",),
            ).fetchone()

            assert row["cwd"] == "/home/user/project"
            assert json.loads(row["env_delta_json"]) == {"FOO": "bar", "BAZ": "qux"}
            assert row["state_version"] == 1

    def test_state_persists_across_retrieval(self, store):
        """Test that state persists when terminal is retrieved again."""
        terminal = _wrap(store, store.create("term-1", "thread-1", "lease-1", "/home/user"))

        # Update state
        new_state = TerminalState(cwd="/home/user/project", env_delta={"FOO": "bar"})
        terminal.update_state(new_state)

        # Retrieve terminal again
        terminal2 = _wrap(store, store.get_active("thread-1"))
        assert terminal2 is not None
        assert terminal2.get_state().cwd == "/home/user/project"
        assert terminal2.get_state().env_delta == {"FOO": "bar"}
        assert terminal2.get_state().state_version == 1

    def test_multiple_state_updates(self, store):
        """Test multiple state updates increment version correctly."""
        terminal = _wrap(store, store.create("term-1", "thread-1", "lease-1", "/home/user"))

        # Update 1
        terminal.update_state(TerminalState(cwd="/home/user/project1"))
        assert terminal.get_state().state_version == 1

        # Update 2
        terminal.update_state(TerminalState(cwd="/home/user/project2"))
        assert terminal.get_state().state_version == 2

        # Update 3
        terminal.update_state(TerminalState(cwd="/home/user/project3", env_delta={"FOO": "bar"}))
        assert terminal.get_state().state_version == 3

        # Verify final state
        state = terminal.get_state()
        assert state.cwd == "/home/user/project3"
        assert state.env_delta == {"FOO": "bar"}
        assert state.state_version == 3


class TestTerminalIntegration:
    """Integration tests for terminal lifecycle."""

    def test_full_lifecycle(self, store):
        """Test complete terminal lifecycle: create → update → retrieve → delete."""
        # Create
        terminal = _wrap(store, store.create("term-1", "thread-1", "lease-1", "/home/user"))
        assert terminal.get_state().cwd == "/home/user"

        # Update state multiple times
        terminal.update_state(TerminalState(cwd="/home/user/project"))
        terminal.update_state(TerminalState(cwd="/home/user/project/src", env_delta={"PATH": "/usr/local/bin"}))

        # Retrieve and verify
        terminal2 = _wrap(store, store.get_active("thread-1"))
        assert terminal2 is not None
        assert terminal2.get_state().cwd == "/home/user/project/src"
        assert terminal2.get_state().env_delta == {"PATH": "/usr/local/bin"}
        assert terminal2.get_state().state_version == 2

        # Delete
        store.delete("term-1")
        assert store.get_active("thread-1") is None

    def test_multiple_terminals_different_leases(self, store):
        """Test multiple terminals can point to different leases."""
        term1 = _wrap(store, store.create("term-1", "thread-1", "lease-1", "/home/user1"))
        term2 = _wrap(store, store.create("term-2", "thread-2", "lease-2", "/home/user2"))
        term3 = _wrap(store, store.create("term-3", "thread-3", "lease-1", "/home/user3"))

        # Verify all created
        assert store.get_active("thread-1") is not None
        assert store.get_active("thread-2") is not None
        assert store.get_active("thread-3") is not None

        # Verify lease associations
        assert term1.lease_id == "lease-1"
        assert term2.lease_id == "lease-2"
        assert term3.lease_id == "lease-1"

    def test_state_isolation_between_terminals(self, store):
        """Test that state updates are isolated between terminals."""
        term1 = _wrap(store, store.create("term-1", "thread-1", "lease-1", "/home/user1"))
        _term2 = _wrap(store, store.create("term-2", "thread-2", "lease-1", "/home/user2"))

        # Update term1 state
        term1.update_state(TerminalState(cwd="/home/user1/project", env_delta={"FOO": "bar"}))

        # Verify term2 state unchanged
        term2_retrieved = _wrap(store, store.get_active("thread-2"))
        assert term2_retrieved.get_state().cwd == "/home/user2"
        assert term2_retrieved.get_state().env_delta == {}
        assert term2_retrieved.get_state().state_version == 0
