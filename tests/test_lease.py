"""Unit tests for SandboxLease and SQLiteLeaseRepo."""

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sandbox.lease import (
    SandboxInstance,
    lease_from_row,
)
from sandbox.provider import SessionInfo
from storage.providers.sqlite.lease_repo import SQLiteLeaseRepo


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    db_path.unlink(missing_ok=True)


@pytest.fixture
def store(temp_db):
    """Create SQLiteLeaseRepo with temp database."""
    return SQLiteLeaseRepo(db_path=temp_db)


@pytest.fixture
def mock_provider():
    """Create mock SandboxProvider."""
    provider = MagicMock()
    provider.name = "test-provider"
    return provider


def _create_lease(store, lease_id, provider_name, volume_id=None):
    """Create lease via repo and return as domain object."""
    row = store.create(lease_id, provider_name, volume_id=volume_id)
    return lease_from_row(row, store.db_path)


def _get_lease(store, lease_id):
    """Get lease via repo and return as domain object."""
    row = store.get(lease_id)
    if row is None:
        return None
    return lease_from_row(row, store.db_path)


class TestSandboxInstance:
    """Test SandboxInstance dataclass."""

    def test_create_instance(self):
        """Test creating SandboxInstance."""
        now = datetime.now()
        instance = SandboxInstance(
            instance_id="inst-123",
            provider_name="e2b",
            status="running",
            created_at=now,
        )

        assert instance.instance_id == "inst-123"
        assert instance.provider_name == "e2b"
        assert instance.status == "running"
        assert instance.created_at == now


class TestLeaseRepo:
    """Test SQLiteLeaseRepo CRUD operations."""

    def test_ensure_tables(self, temp_db):
        """Test table creation."""
        SQLiteLeaseRepo(db_path=temp_db)

        # Verify table exists
        with sqlite3.connect(str(temp_db)) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sandbox_leases'")
            assert cursor.fetchone() is not None

    def test_create_lease(self, store):
        """Test creating a new lease."""
        lease = _create_lease(store, "lease-123", "e2b")

        assert lease.lease_id == "lease-123"
        assert lease.provider_name == "e2b"
        assert lease.get_instance() is None
        assert lease.needs_refresh is False
        assert lease.refresh_hint_at is None

    def test_get_lease(self, store):
        """Test retrieving lease by lease_id."""
        store.create(lease_id="lease-123", provider_name="e2b")

        row = store.get("lease-123")
        assert row is not None
        assert row["lease_id"] == "lease-123"
        assert row["provider_name"] == "e2b"

    def test_get_nonexistent_lease(self, store):
        """Test retrieving non-existent lease returns None."""
        lease = store.get("nonexistent-lease")
        assert lease is None

    def test_delete_lease(self, store):
        """Test deleting a lease."""
        store.create(lease_id="lease-123", provider_name="e2b")

        # Verify exists
        assert store.get("lease-123") is not None

        # Delete
        store.delete("lease-123")

        # Verify deleted
        assert store.get("lease-123") is None

    def test_list_all_leases(self, store):
        """Test listing all leases."""
        import time

        store.create("lease-1", "e2b")
        time.sleep(0.01)
        store.create("lease-2", "agentbay")
        time.sleep(0.01)
        store.create("lease-3", "e2b")

        leases = store.list_all()
        assert len(leases) == 3

        # Should be ordered by created_at DESC
        assert leases[0]["lease_id"] == "lease-3"
        assert leases[1]["lease_id"] == "lease-2"
        assert leases[2]["lease_id"] == "lease-1"

    def test_list_by_provider(self, store):
        """Test listing leases by provider."""
        store.create("lease-1", "e2b")
        store.create("lease-2", "agentbay")
        store.create("lease-3", "e2b")

        e2b_leases = store.list_by_provider("e2b")
        assert len(e2b_leases) == 2
        assert all(lease["provider_name"] == "e2b" for lease in e2b_leases)

        agentbay_leases = store.list_by_provider("agentbay")
        assert len(agentbay_leases) == 1
        assert agentbay_leases[0]["provider_name"] == "agentbay"

    def test_find_by_instance(self, store, mock_provider):
        lease = _create_lease(store, "lease-1", "test-provider")
        mock_provider.create_session.return_value = SessionInfo(
            session_id="inst-lookup",
            provider="test-provider",
            status="running",
        )
        lease.ensure_active_instance(mock_provider)

        found_row = store.find_by_instance(provider_name="test-provider", instance_id="inst-lookup")
        assert found_row is not None
        assert found_row["lease_id"] == "lease-1"


class TestSQLiteLease:
    """Test SQLiteLease instance management."""

    def test_ensure_active_instance_creates_new(self, store, mock_provider):
        """Test ensure_active_instance creates new instance when none exists."""
        lease = _create_lease(store, "lease-1", "test-provider")

        # Mock provider to return new session
        mock_provider.create_session.return_value = SessionInfo(
            session_id="inst-123",
            provider="test-provider",
            status="running",
        )

        instance = lease.ensure_active_instance(mock_provider)

        assert instance.instance_id == "inst-123"
        assert instance.status == "running"
        assert lease.get_instance() == instance
        mock_provider.create_session.assert_called_once()

    def test_ensure_active_instance_reuses_running(self, store, mock_provider):
        """Test ensure_active_instance reuses running instance."""
        lease = _create_lease(store, "lease-1", "test-provider")

        # Create initial instance
        mock_provider.create_session.return_value = SessionInfo(
            session_id="inst-123",
            provider="test-provider",
            status="running",
        )
        instance1 = lease.ensure_active_instance(mock_provider)

        # Mock provider to report instance is still running
        mock_provider.get_session_status.return_value = "running"

        # Call again - should reuse
        instance2 = lease.ensure_active_instance(mock_provider)

        assert instance2.instance_id == instance1.instance_id
        assert mock_provider.create_session.call_count == 1  # Only called once
        assert mock_provider.get_session_status.call_count == 0

    def test_ensure_active_instance_converges_stale_paused_state(self, store, mock_provider):
        """If DB says paused but provider says running, lease status must converge to running."""
        lease = _create_lease(store, "lease-1", "test-provider")

        mock_provider.create_session.return_value = SessionInfo(
            session_id="inst-123",
            provider="test-provider",
            status="running",
        )
        lease.ensure_active_instance(mock_provider)

        mock_provider.pause_session.return_value = True
        lease.pause_instance(mock_provider)
        assert lease.get_instance().status == "paused"

        mock_provider.get_session_status.return_value = "running"
        instance = lease.ensure_active_instance(mock_provider)
        assert instance.status == "running"

        reloaded = _get_lease(store, "lease-1")
        assert reloaded is not None
        assert reloaded.get_instance() is not None
        assert reloaded.get_instance().status == "running"

    def test_invalidation_forces_refresh_even_when_snapshot_fresh(self, store, mock_provider):
        lease = _create_lease(store, "lease-1", "test-provider")
        mock_provider.create_session.return_value = SessionInfo(
            session_id="inst-123",
            provider="test-provider",
            status="running",
        )
        lease.ensure_active_instance(mock_provider)
        assert lease.needs_refresh is False

        lease.mark_needs_refresh()
        assert lease.needs_refresh is True

        mock_provider.get_session_status.return_value = "running"
        lease.ensure_active_instance(mock_provider)

        assert mock_provider.get_session_status.call_count == 1
        assert lease.needs_refresh is False

    def test_store_mark_needs_refresh(self, store):
        _create_lease(store, "lease-1", "test-provider")
        updated = store.mark_needs_refresh(lease_id="lease-1")
        assert updated is True

        reloaded = _get_lease(store, "lease-1")
        assert reloaded is not None
        assert reloaded.needs_refresh is True
        assert reloaded.refresh_hint_at is not None

    def test_destroy_instance(self, store, mock_provider):
        """Test destroying instance."""
        lease = _create_lease(store, "lease-1", "test-provider")

        # Create instance
        mock_provider.create_session.return_value = SessionInfo(
            session_id="inst-123",
            provider="test-provider",
            status="running",
        )
        lease.ensure_active_instance(mock_provider)

        # Destroy
        lease.destroy_instance(mock_provider)

        assert lease.get_instance() is None
        mock_provider.destroy_session.assert_called_once_with("inst-123")

    def test_pause_instance(self, store, mock_provider):
        """Test pausing instance."""
        lease = _create_lease(store, "lease-1", "test-provider")

        # Create instance
        mock_provider.create_session.return_value = SessionInfo(
            session_id="inst-123",
            provider="test-provider",
            status="running",
        )
        lease.ensure_active_instance(mock_provider)

        # Pause
        mock_provider.pause_session.return_value = True
        result = lease.pause_instance(mock_provider)

        assert result is True
        assert lease.get_instance().status == "paused"
        mock_provider.pause_session.assert_called_once_with("inst-123")

    def test_resume_instance(self, store, mock_provider):
        """Test resuming instance."""
        lease = _create_lease(store, "lease-1", "test-provider")

        # Create and pause instance
        mock_provider.create_session.return_value = SessionInfo(
            session_id="inst-123",
            provider="test-provider",
            status="running",
        )
        lease.ensure_active_instance(mock_provider)
        mock_provider.pause_session.return_value = True
        lease.pause_instance(mock_provider)

        # Resume
        mock_provider.resume_session.return_value = True
        result = lease.resume_instance(mock_provider)

        assert result is True
        assert lease.get_instance().status == "running"
        mock_provider.resume_session.assert_called_once_with("inst-123")

    def test_instance_persists_across_retrieval(self, store, mock_provider):
        """Test that instance persists when lease is retrieved again."""
        lease = _create_lease(store, "lease-1", "test-provider")

        # Create instance
        mock_provider.create_session.return_value = SessionInfo(
            session_id="inst-123",
            provider="test-provider",
            status="running",
        )
        lease.ensure_active_instance(mock_provider)

        # Retrieve lease again
        lease2 = _get_lease(store, "lease-1")
        assert lease2 is not None
        instance = lease2.get_instance()
        assert instance is not None
        assert instance.instance_id == "inst-123"
        assert instance.status == "running"

    def test_apply_rolls_back_state_when_event_insert_conflicts(self, store, mock_provider):
        """Snapshot/metadata updates must roll back when event append fails."""
        lease = _create_lease(store, "lease-atomic", "test-provider")
        lease.apply(
            mock_provider,
            event_type="provider.error",
            source="test.seed",
            payload={"error": "seed"},
            event_id="evt-duplicate",
        )

        before = _get_lease(store, "lease-atomic")
        assert before is not None

        with pytest.raises(sqlite3.IntegrityError):
            lease.apply(
                mock_provider,
                event_type="provider.error",
                source="test.conflict",
                payload={"error": "boom"},
                event_id="evt-duplicate",
            )

        after = _get_lease(store, "lease-atomic")
        assert after is not None
        assert after.version == before.version
        assert after.last_error == before.last_error
        assert after.needs_refresh == before.needs_refresh
        assert after.observed_state == before.observed_state

        with sqlite3.connect(str(store.db_path), timeout=30) as conn:
            count_row = conn.execute(
                "SELECT COUNT(*) FROM lease_events WHERE event_id = ?",
                ("evt-duplicate",),
            ).fetchone()
        assert count_row is not None
        assert int(count_row[0]) == 1


class TestLeaseIntegration:
    """Integration tests for lease lifecycle."""

    def test_full_lifecycle(self, store, mock_provider):
        """Test complete lease lifecycle: create -> instance -> pause -> resume -> destroy."""
        # Create lease
        lease = _create_lease(store, "lease-1", "test-provider")
        assert lease.get_instance() is None

        # Create instance
        mock_provider.create_session.return_value = SessionInfo(
            session_id="inst-123",
            provider="test-provider",
            status="running",
        )
        instance = lease.ensure_active_instance(mock_provider)
        assert instance.instance_id == "inst-123"

        # Pause
        mock_provider.pause_session.return_value = True
        lease.pause_instance(mock_provider)
        assert lease.get_instance().status == "paused"

        # Resume
        mock_provider.resume_session.return_value = True
        lease.resume_instance(mock_provider)
        assert lease.get_instance().status == "running"

        # Destroy
        lease.destroy_instance(mock_provider)
        assert lease.get_instance() is None

        # Delete lease
        store.delete("lease-1")
        assert store.get("lease-1") is None

    def test_multiple_leases_different_providers(self, store):
        """Test multiple leases with different providers."""
        lease1 = _create_lease(store, "lease-1", "e2b")
        lease2 = _create_lease(store, "lease-2", "agentbay")
        lease3 = _create_lease(store, "lease-3", "e2b")

        assert lease1.provider_name == "e2b"
        assert lease2.provider_name == "agentbay"
        assert lease3.provider_name == "e2b"

        # Verify all created
        assert store.get("lease-1") is not None
        assert store.get("lease-2") is not None
        assert store.get("lease-3") is not None
