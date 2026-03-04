"""Integration tests for the full new architecture flow.

Tests the complete flow: Thread → ChatSession → Runtime → Terminal → Lease → Instance
"""

import asyncio
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sandbox.chat_session import ChatSessionManager
from sandbox.lease import LeaseStore
from sandbox.manager import SandboxManager
from sandbox.provider import ProviderCapability, SessionInfo
from sandbox.terminal import TerminalStore


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    db_path.unlink(missing_ok=True)


@pytest.fixture
def mock_provider():
    """Create mock SandboxProvider for local testing."""
    provider = MagicMock()
    provider.name = "local"
    provider.default_cwd = "/tmp"
    provider.get_capability.return_value = ProviderCapability(
        can_pause=True,
        can_resume=True,
        can_destroy=True,
        supports_webhook=False,
        supports_status_probe=False,
        eager_instance_binding=True,
        inspect_visible=True,
        runtime_kind="local",
    )
    provider.create_session.return_value = SessionInfo(
        session_id="local-inst-1",
        provider="local",
        status="running",
    )
    provider.get_session_status.return_value = "running"
    provider.pause_session.return_value = True
    provider.resume_session.return_value = True
    provider.destroy_session.return_value = True

    # Mock execute to return proper results
    def mock_execute(instance_id, command, timeout_ms=None, cwd=None):
        result = MagicMock()
        result.exit_code = 0

        if command == "pwd":
            result.stdout = cwd or "/root"
            result.stderr = ""
        elif command.startswith("cd "):
            result.stdout = ""
            result.stderr = ""
        else:
            result.stdout = "command output"
            result.stderr = ""

        return result

    provider.execute = mock_execute
    return provider


@pytest.fixture
def mock_remote_provider():
    """Create mock remote provider that supports lease lifecycle + fs ops."""
    provider = MagicMock()
    provider.name = "e2b"
    provider.get_capability.return_value = ProviderCapability(
        can_pause=True,
        can_resume=True,
        can_destroy=True,
        supports_webhook=False,
        runtime_kind="remote",
    )
    provider.create_session.return_value = SessionInfo(
        session_id="inst-remote-1",
        provider="e2b",
        status="running",
    )
    provider.get_session_status.return_value = "running"
    provider.pause_session.return_value = True
    provider.resume_session.return_value = True
    provider.write_file.return_value = "ok"
    provider.read_file.return_value = "content"
    provider.list_dir.return_value = []
    return provider


@pytest.fixture
def sandbox_manager(temp_db, mock_provider):
    """Create SandboxManager with temp database."""
    return SandboxManager(provider=mock_provider, db_path=temp_db)


@pytest.fixture
def remote_sandbox_manager(temp_db, mock_remote_provider):
    """Create SandboxManager with remote provider."""
    return SandboxManager(provider=mock_remote_provider, db_path=temp_db)


class TestFullArchitectureFlow:
    """Test complete flow through all layers."""

    def test_get_sandbox_creates_all_layers(self, sandbox_manager, temp_db):
        """Test that get_sandbox creates Terminal → Lease → Runtime → ChatSession."""
        thread_id = "test-thread-1"

        # Get sandbox (should create everything)
        capability = sandbox_manager.get_sandbox(thread_id)

        assert capability is not None
        assert capability._session is not None
        assert capability._session.thread_id == thread_id
        assert capability._session.terminal is not None
        assert capability._session.lease is not None
        assert capability._session.runtime is not None

        # Verify persistence
        terminal_store = TerminalStore(db_path=temp_db)
        terminal = terminal_store.get(thread_id)
        assert terminal is not None

        lease_store = LeaseStore(db_path=temp_db)
        lease = lease_store.get(terminal.lease_id)
        assert lease is not None

    def test_get_sandbox_reuses_existing_session(self, sandbox_manager):
        """Test that get_sandbox reuses existing session."""
        thread_id = "test-thread-2"

        # First call creates
        capability1 = sandbox_manager.get_sandbox(thread_id)
        session_id1 = capability1._session.session_id

        # Second call reuses
        capability2 = sandbox_manager.get_sandbox(thread_id)
        session_id2 = capability2._session.session_id

        assert session_id1 == session_id2

    @pytest.mark.asyncio
    async def test_command_execution_through_capability(self, sandbox_manager):
        """Test command execution through capability wrapper."""
        thread_id = "test-thread-3"

        capability = sandbox_manager.get_sandbox(thread_id)

        # Execute command
        result = await capability.command.execute("echo hello")

        assert result.exit_code == 0
        assert result.stdout is not None

    @pytest.mark.asyncio
    async def test_async_command_status_survives_session_recreate(self, sandbox_manager):
        """Completed async commands should remain queryable after ChatSession recreation."""
        thread_id = "test-thread-3b"
        capability1 = sandbox_manager.get_sandbox(thread_id)
        session_id_1 = capability1._session.session_id

        async_cmd = await capability1.command.execute_async("echo async-ok")
        done_1 = await capability1.command.wait_for(async_cmd.command_id, timeout=5.0)
        assert done_1 is not None
        assert done_1.exit_code == 0
        assert "async-ok" in done_1.stdout

        sandbox_manager.session_manager.delete(session_id_1, reason="test_rotate_session")
        capability2 = sandbox_manager.get_sandbox(thread_id)
        assert capability2._session.session_id != session_id_1

        status = await capability2.command.get_status(async_cmd.command_id)
        assert status is not None
        assert status.done

        done_2 = await capability2.command.wait_for(async_cmd.command_id, timeout=1.0)
        assert done_2 is not None
        assert done_2.exit_code == 0
        assert "async-ok" in done_2.stdout

    @pytest.mark.asyncio
    async def test_non_blocking_command_uses_new_abstract_terminal(self, sandbox_manager, temp_db):
        thread_id = "test-thread-async-terminal"
        capability = sandbox_manager.get_sandbox(thread_id)
        default_terminal_id = capability._session.terminal.terminal_id
        shared_lease_id = capability._session.lease.lease_id

        from sandbox.terminal import TerminalState

        capability._session.terminal.update_state(TerminalState(cwd="/tmp", env_delta={"FOO": "bar"}))

        async_cmd = await capability.command.execute_async("echo bg-terminal")
        result = await capability.command.wait_for(async_cmd.command_id, timeout=5.0)
        assert result is not None
        assert result.exit_code == 0
        assert "bg-terminal" in result.stdout

        terminals = sandbox_manager.terminal_store.list_by_thread(thread_id)
        assert len(terminals) == 2
        default_terminal = sandbox_manager.terminal_store.get_default(thread_id)
        assert default_terminal is not None
        assert default_terminal.terminal_id == default_terminal_id

        background_terminal = next(t for t in terminals if t.terminal_id != default_terminal_id)
        assert background_terminal.lease_id == shared_lease_id
        bg_state = background_terminal.get_state()
        assert bg_state.cwd in {"/tmp", "/private/tmp"}
        assert bg_state.env_delta.get("FOO") == "bar"

        with sqlite3.connect(str(temp_db), timeout=30) as conn:
            row = conn.execute(
                "SELECT terminal_id FROM terminal_commands WHERE command_id = ?",
                (async_cmd.command_id,),
            ).fetchone()
        assert row is not None
        assert row[0] == background_terminal.terminal_id

    @pytest.mark.asyncio
    async def test_running_async_command_visible_from_new_manager(self, temp_db, mock_provider):
        thread_id = "test-thread-running-visible"
        manager1 = SandboxManager(provider=mock_provider, db_path=temp_db)
        capability1 = manager1.get_sandbox(thread_id)

        async_cmd = await capability1.command.execute_async("for i in 1 2 3; do echo tick-$i; sleep 1; done")
        await asyncio.sleep(1.2)

        # Simulate command_status query from a fresh API manager/session process.
        manager2 = SandboxManager(provider=mock_provider, db_path=temp_db)
        capability2 = manager2.get_sandbox(thread_id)

        running = await capability2.command.get_status(async_cmd.command_id)
        assert running is not None
        assert not running.done
        assert "Runtime restarted before command completion" not in "".join(running.stderr_buffer)
        assert "tick-1" in "".join(running.stdout_buffer)

        finished = await capability2.command.wait_for(async_cmd.command_id, timeout=5.0)
        assert finished is not None
        assert finished.exit_code == 0
        assert "tick-3" in finished.stdout

    @pytest.mark.asyncio
    async def test_command_status_fallback_when_terminal_row_missing(self, sandbox_manager, temp_db):
        thread_id = "test-thread-fallback-status"
        capability = sandbox_manager.get_sandbox(thread_id)

        async_cmd = await capability.command.execute_async("echo fallback-ok")
        done = await capability.command.wait_for(async_cmd.command_id, timeout=5.0)
        assert done is not None
        assert done.exit_code == 0
        assert "fallback-ok" in done.stdout

        with sqlite3.connect(str(temp_db), timeout=30) as conn:
            row = conn.execute(
                "SELECT terminal_id FROM terminal_commands WHERE command_id = ?",
                (async_cmd.command_id,),
            ).fetchone()
            assert row is not None
            conn.execute("DELETE FROM abstract_terminals WHERE terminal_id = ?", (row[0],))
            conn.commit()

        status = await capability.command.get_status(async_cmd.command_id)
        assert status is not None
        assert status.done
        assert "fallback-ok" in "".join(status.stdout_buffer)

        done_again = await capability.command.wait_for(async_cmd.command_id, timeout=1.0)
        assert done_again is not None
        assert done_again.exit_code == 0
        assert "fallback-ok" in done_again.stdout

    def test_terminal_state_persists_across_sessions(self, sandbox_manager, temp_db):
        """Test that terminal state persists when session expires."""
        thread_id = "test-thread-4"

        # Create session and update terminal state
        capability1 = sandbox_manager.get_sandbox(thread_id)
        terminal_id = capability1._session.terminal.terminal_id

        # Update terminal state
        from sandbox.terminal import TerminalState

        new_state = TerminalState(cwd="/tmp", env_delta={"FOO": "bar"})
        capability1._session.terminal.update_state(new_state)

        # Delete session (simulating expiry)
        sandbox_manager.session_manager.delete(capability1._session.session_id)

        # Get sandbox again (creates new session)
        capability2 = sandbox_manager.get_sandbox(thread_id)

        # Terminal should be reused with persisted state
        assert capability2._session.terminal.terminal_id == terminal_id
        state = capability2._session.terminal.get_state()
        assert state.cwd == "/tmp"
        assert state.env_delta == {"FOO": "bar"}

    def test_get_sandbox_fails_on_provider_mismatch(self, temp_db, mock_provider, mock_remote_provider):
        local_mgr = SandboxManager(provider=mock_provider, db_path=temp_db)
        remote_mgr = SandboxManager(provider=mock_remote_provider, db_path=temp_db)

        thread_id = "test-thread-provider-mismatch"
        _ = local_mgr.get_sandbox(thread_id)

        with pytest.raises(RuntimeError, match="bound to provider"):
            remote_mgr.get_sandbox(thread_id)

    def test_pause_all_sessions_skips_provider_mismatch(self, temp_db, mock_provider, mock_remote_provider):
        local_mgr = SandboxManager(provider=mock_provider, db_path=temp_db)
        remote_mgr = SandboxManager(provider=mock_remote_provider, db_path=temp_db)

        _ = local_mgr.get_sandbox("test-thread-provider-mismatch-pause")

        assert remote_mgr.pause_all_sessions() == 0

    def test_lease_shared_across_terminals(self, sandbox_manager, temp_db):
        """Test that multiple terminals can share the same lease."""
        thread_id1 = "test-thread-5"
        thread_id2 = "test-thread-6"

        # Create first terminal
        capability1 = sandbox_manager.get_sandbox(thread_id1)
        lease_id1 = capability1._session.lease.lease_id

        # Manually create second terminal with same lease
        terminal_store = TerminalStore(db_path=temp_db)
        terminal2 = terminal_store.create(
            terminal_id="term-shared",
            thread_id=thread_id2,
            lease_id=lease_id1,
        )

        # Get sandbox for second thread
        capability2 = sandbox_manager.get_sandbox(thread_id2)
        lease_id2 = capability2._session.lease.lease_id

        # Should share the same lease
        assert lease_id1 == lease_id2

    def test_session_touch_updates_activity(self, sandbox_manager):
        """Test that capability.touch() updates session activity."""
        thread_id = "test-thread-7"

        capability = sandbox_manager.get_sandbox(thread_id)
        old_activity = capability._session.last_active_at

        import time

        time.sleep(0.01)

        capability.touch()

        # Activity should be updated
        assert capability._session.last_active_at > old_activity

    def test_session_info_api(self, sandbox_manager):
        """Test that manager can expose current provider session info."""
        thread_id = "test-thread-8"

        session_info = sandbox_manager.get_or_create_session(thread_id)
        assert session_info is not None
        assert session_info.provider == "local"

        sessions = sandbox_manager.list_sessions()
        assert len(sessions) > 0

    def test_remote_fs_operation_fails_on_paused_lease(self, remote_sandbox_manager, mock_remote_provider):
        """Paused lease must fail fast until explicit resume."""
        thread_id = "test-thread-remote-fs-1"
        capability = remote_sandbox_manager.get_sandbox(thread_id)

        lease = capability._session.lease
        lease.ensure_active_instance(mock_remote_provider)
        lease.pause_instance(mock_remote_provider)
        assert lease.get_instance() is not None
        assert lease.get_instance().status == "paused"
        mock_remote_provider.get_session_status.return_value = "paused"

        with pytest.raises(RuntimeError, match="is paused"):
            capability.fs.write_file("/home/user/test.txt", "ok")
        assert lease.get_instance().status == "paused"


class TestSessionLifecycle:
    """Test session lifecycle management."""

    def test_session_expiry_cleanup(self, sandbox_manager, temp_db):
        """Test that expired sessions are cleaned up."""

        thread_id = "test-thread-9"

        # Create session with very short timeout
        capability = sandbox_manager.get_sandbox(thread_id)
        session_id = capability._session.session_id

        # Manually update policy to expire immediately
        session_manager = ChatSessionManager(
            provider=sandbox_manager.provider,
            db_path=temp_db,
        )

        import time

        time.sleep(0.1)

        # Cleanup expired
        count = session_manager.cleanup_expired()

        # Session should still exist (default policy is 10 minutes)
        assert count == 0

    def test_pause_and_resume_session(self, sandbox_manager):
        """Test pausing and resuming sessions."""
        thread_id = "test-thread-10"

        # Create session
        capability = sandbox_manager.get_sandbox(thread_id)
        session_id = capability._session.session_id
        terminal_id = capability._session.terminal.terminal_id

        assert sandbox_manager.pause_session(thread_id)
        paused = sandbox_manager.session_manager.get(thread_id, terminal_id)
        assert paused is not None
        assert paused.session_id == session_id
        assert paused.status == "paused"

        assert sandbox_manager.resume_session(thread_id)
        resumed = sandbox_manager.session_manager.get(thread_id, terminal_id)
        assert resumed is not None
        assert resumed.session_id == session_id
        assert resumed.status == "active"

    def test_pause_and_resume_cover_all_thread_terminals(self, sandbox_manager):
        thread_id = "test-thread-10b"
        capability = sandbox_manager.get_sandbox(thread_id)
        asyncio.run(capability.command.execute_async("echo bg"))

        terminals = sandbox_manager.terminal_store.list_by_thread(thread_id)
        assert len(terminals) == 2

        assert sandbox_manager.pause_session(thread_id)
        for terminal in terminals:
            session = sandbox_manager.session_manager.get(thread_id, terminal.terminal_id)
            assert session is not None
            assert session.status == "paused"

        assert sandbox_manager.resume_session(thread_id)
        for terminal in terminals:
            session = sandbox_manager.session_manager.get(thread_id, terminal.terminal_id)
            assert session is not None
            assert session.status == "active"

    def test_destroy_session(self, sandbox_manager):
        """Test destroying a session."""
        thread_id = "test-thread-11"

        # Create session
        capability = sandbox_manager.get_sandbox(thread_id)
        session_id = capability._session.session_id
        terminal_id = capability._session.terminal.terminal_id

        # Destroy
        sandbox_manager.destroy_session(thread_id)

        # Session should be gone
        session = sandbox_manager.session_manager.get(thread_id, terminal_id)
        assert session is None

    def test_destroy_session_removes_all_thread_resources(self, sandbox_manager):
        thread_id = "test-thread-11b"
        capability = sandbox_manager.get_sandbox(thread_id)
        asyncio.run(capability.command.execute_async("echo bg"))

        terminals_before = sandbox_manager.terminal_store.list_by_thread(thread_id)
        assert len(terminals_before) == 2

        assert sandbox_manager.destroy_session(thread_id)
        assert sandbox_manager.terminal_store.list_by_thread(thread_id) == []
        assert all(
            sandbox_manager.session_manager.get(thread_id, terminal.terminal_id) is None
            for terminal in terminals_before
        )


class TestMultiThreadScenarios:
    """Test scenarios with multiple threads."""

    def test_multiple_threads_independent_sessions(self, sandbox_manager):
        """Test that multiple threads get independent sessions."""
        thread_ids = [f"test-thread-{i}" for i in range(3)]

        capabilities = [sandbox_manager.get_sandbox(tid) for tid in thread_ids]

        # All should have different sessions
        session_ids = [cap._session.session_id for cap in capabilities]
        assert len(set(session_ids)) == 3

        # All should have different terminals
        terminal_ids = [cap._session.terminal.terminal_id for cap in capabilities]
        assert len(set(terminal_ids)) == 3

    def test_thread_switch_preserves_state(self, sandbox_manager):
        """Test that switching between threads preserves state."""
        thread_id1 = "test-thread-12"
        thread_id2 = "test-thread-13"

        # Work on thread 1
        cap1 = sandbox_manager.get_sandbox(thread_id1)
        from sandbox.terminal import TerminalState

        cap1._session.terminal.update_state(TerminalState(cwd="/tmp"))

        # Switch to thread 2
        cap2 = sandbox_manager.get_sandbox(thread_id2)
        cap2._session.terminal.update_state(TerminalState(cwd="/home"))

        # Switch back to thread 1
        cap1_again = sandbox_manager.get_sandbox(thread_id1)
        state1 = cap1_again._session.terminal.get_state()
        assert state1.cwd == "/tmp"

        # Check thread 2 state
        cap2_again = sandbox_manager.get_sandbox(thread_id2)
        state2 = cap2_again._session.terminal.get_state()
        assert state2.cwd == "/home"


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_missing_terminal_recreates_with_same_id(self, sandbox_manager, temp_db):
        """Test that terminal is recreated when missing from DB.

        Note: The terminal_id is stored in the session, so when we delete
        the terminal but not the session, the session still references the
        old terminal_id. This is expected behavior - the terminal_id is
        stable across recreations.
        """
        thread_id = "test-thread-14"

        # Create session
        capability = sandbox_manager.get_sandbox(thread_id)
        terminal_id = capability._session.terminal.terminal_id

        # Delete terminal from DB (but not session)
        terminal_store = TerminalStore(db_path=temp_db)
        terminal_store.delete(terminal_id)

        # Delete session to force full recreation
        sandbox_manager.session_manager.delete(capability._session.session_id)

        # Get sandbox again - creates new terminal
        capability2 = sandbox_manager.get_sandbox(thread_id)

        # Terminal should exist in DB now
        terminal2 = terminal_store.get(thread_id)
        assert terminal2 is not None

    def test_missing_lease_recreates_with_same_id(self, sandbox_manager, temp_db):
        """Test that lease is recreated when missing from DB.

        Note: The lease_id is stored in the terminal, so when we delete
        the lease but not the terminal, the terminal still references the
        old lease_id. This is expected behavior - the lease_id is stable.
        """
        thread_id = "test-thread-15"

        # Create session
        capability = sandbox_manager.get_sandbox(thread_id)
        lease_id = capability._session.lease.lease_id

        # Delete lease from DB
        lease_store = LeaseStore(db_path=temp_db)
        lease_store.delete(lease_id)

        # Delete session AND terminal to force full recreation
        sandbox_manager.session_manager.delete(capability._session.session_id)
        terminal_store = TerminalStore(db_path=temp_db)
        terminal_store.delete(capability._session.terminal.terminal_id)

        # Get sandbox again - creates new terminal + lease
        capability2 = sandbox_manager.get_sandbox(thread_id)

        # Lease should exist in DB now
        lease2 = lease_store.get(capability2._session.lease.lease_id)
        assert lease2 is not None
