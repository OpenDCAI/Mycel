"""Unit tests for SummaryStore."""

import sqlite3
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from core.runtime.middleware.memory.summary_store import SummaryStore


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    # Cleanup
    if db_path.exists():
        db_path.unlink()
    # Also cleanup WAL files
    for suffix in ["-wal", "-shm"]:
        wal_file = Path(str(db_path) + suffix)
        if wal_file.exists():
            wal_file.unlink()


def test_save_and_get_summary(temp_db):
    """Test saving and retrieving a summary."""
    store = SummaryStore(temp_db)

    # Save a summary
    summary_id = store.save_summary(
        thread_id="test-thread-1",
        summary_text="This is a test summary",
        compact_up_to_index=10,
        compacted_at=20,
    )

    assert summary_id.startswith("test-thread-1_")

    # Retrieve the summary
    summary = store.get_latest_summary("test-thread-1")

    assert summary is not None
    assert summary.thread_id == "test-thread-1"
    assert summary.summary_text == "This is a test summary"
    assert summary.compact_up_to_index == 10
    assert summary.compacted_at == 20
    assert summary.is_split_turn is False
    assert summary.split_turn_prefix is None
    assert summary.is_active is True


def test_multiple_summaries_only_latest_active(temp_db):
    """Test that only the latest summary is active."""
    store = SummaryStore(temp_db)

    # Save first summary
    _id1 = store.save_summary(
        thread_id="test-thread-2",
        summary_text="First summary",
        compact_up_to_index=10,
        compacted_at=20,
    )

    # Save second summary
    id2 = store.save_summary(
        thread_id="test-thread-2",
        summary_text="Second summary",
        compact_up_to_index=30,
        compacted_at=40,
    )

    # Only the latest should be active
    latest = store.get_latest_summary("test-thread-2")
    assert latest is not None
    assert latest.summary_id == id2
    assert latest.summary_text == "Second summary"
    assert latest.is_active is True

    # List all summaries
    all_summaries = store.list_summaries("test-thread-2")
    assert len(all_summaries) == 2

    # Check that first is inactive
    active_count = sum(1 for s in all_summaries if s["is_active"])
    assert active_count == 1


def test_split_turn_summary(temp_db):
    """Test saving and retrieving a split turn summary."""
    store = SummaryStore(temp_db)

    # Save a split turn summary
    summary_id = store.save_summary(  # noqa: F841
        thread_id="test-thread-3",
        summary_text="Combined summary with split turn",
        compact_up_to_index=15,
        compacted_at=30,
        is_split_turn=True,
        split_turn_prefix="Prefix summary",
    )

    # Retrieve the summary
    summary = store.get_latest_summary("test-thread-3")

    assert summary is not None
    assert summary.is_split_turn is True
    assert summary.split_turn_prefix == "Prefix summary"
    assert "Combined summary with split turn" in summary.summary_text


def test_no_summary_returns_none(temp_db):
    """Test that getting a non-existent summary returns None."""
    store = SummaryStore(temp_db)

    summary = store.get_latest_summary("non-existent-thread")
    assert summary is None


def test_delete_thread_summaries(temp_db):
    """Test deleting all summaries for a thread."""
    store = SummaryStore(temp_db)

    # Save multiple summaries
    store.save_summary(
        thread_id="test-thread-4",
        summary_text="Summary 1",
        compact_up_to_index=10,
        compacted_at=20,
    )
    store.save_summary(
        thread_id="test-thread-4",
        summary_text="Summary 2",
        compact_up_to_index=30,
        compacted_at=40,
    )

    # Verify they exist
    assert len(store.list_summaries("test-thread-4")) == 2

    # Delete all summaries
    store.delete_thread_summaries("test-thread-4")

    # Verify they're gone
    assert len(store.list_summaries("test-thread-4")) == 0
    assert store.get_latest_summary("test-thread-4") is None


def test_retry_on_failure(temp_db):
    """Test that save/get operations retry on failure."""
    store = SummaryStore(temp_db)

    # This test verifies the retry mechanism exists
    # In a real scenario, we'd mock sqlite3 to simulate failures
    # For now, we just verify normal operation works
    summary_id = store.save_summary(  # noqa: F841
        thread_id="test-thread-5",
        summary_text="Test retry",
        compact_up_to_index=5,
        compacted_at=10,
        max_retries=3,
    )

    summary = store.get_latest_summary("test-thread-5", max_retries=3)
    assert summary is not None
    assert summary.summary_text == "Test retry"


def test_concurrent_writes(temp_db):
    """Test concurrent writes with 5 threads writing different thread_ids."""
    store = SummaryStore(temp_db)
    results = []
    errors = []

    def write_summary(thread_num):
        try:
            thread_id = f"concurrent-thread-{thread_num}"
            summary_id = store.save_summary(
                thread_id=thread_id,
                summary_text=f"Summary from thread {thread_num}",
                compact_up_to_index=thread_num * 10,
                compacted_at=thread_num * 20,
            )
            results.append((thread_id, summary_id))
        except Exception as e:
            errors.append(e)

    # Launch 5 threads
    threads = []
    for i in range(5):
        t = threading.Thread(target=write_summary, args=(i,))
        threads.append(t)
        t.start()

    # Wait for all threads to complete
    for t in threads:
        t.join()

    # Verify no errors
    assert len(errors) == 0, f"Errors occurred: {errors}"

    # Verify all 5 summaries were saved
    assert len(results) == 5

    # Verify each summary can be retrieved
    for thread_id, summary_id in results:
        summary = store.get_latest_summary(thread_id)
        assert summary is not None
        assert summary.thread_id == thread_id
        assert summary.summary_id == summary_id


def test_concurrent_reads(temp_db):
    """Test concurrent reads with 10 threads reading same thread_id."""
    store = SummaryStore(temp_db)

    # First, save a summary
    store.save_summary(
        thread_id="shared-thread",
        summary_text="Shared summary for concurrent reads",
        compact_up_to_index=100,
        compacted_at=200,
    )

    results = []
    errors = []

    def read_summary():
        try:
            summary = store.get_latest_summary("shared-thread")
            results.append(summary)
        except Exception as e:
            errors.append(e)

    # Launch 10 threads
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(read_summary) for _ in range(10)]
        for future in futures:
            future.result()

    # Verify no errors
    assert len(errors) == 0, f"Errors occurred: {errors}"

    # Verify all 10 reads succeeded
    assert len(results) == 10

    # Verify all reads returned the same data
    for summary in results:
        assert summary is not None
        assert summary.thread_id == "shared-thread"
        assert summary.summary_text == "Shared summary for concurrent reads"
        assert summary.compact_up_to_index == 100
        assert summary.compacted_at == 200


def test_large_summary_text(temp_db):
    """Test saving 1MB summary text."""
    store = SummaryStore(temp_db)

    # Create a 1MB string (1024 * 1024 characters)
    large_text = "A" * (1024 * 1024)

    # Save the large summary
    summary_id = store.save_summary(
        thread_id="large-thread",
        summary_text=large_text,
        compact_up_to_index=1000,
        compacted_at=2000,
    )

    assert summary_id.startswith("large-thread_")

    # Retrieve and verify
    summary = store.get_latest_summary("large-thread")
    assert summary is not None
    assert len(summary.summary_text) == 1024 * 1024
    assert summary.summary_text == large_text


def test_special_characters_in_summary(temp_db):
    """Test Unicode, emoji, and SQL injection characters in summary."""
    store = SummaryStore(temp_db)

    # Test various special characters
    special_text = (
        "Unicode: 你好世界 مرحبا العالم\n"
        "Emoji: 😀🎉🚀💻\n"
        "SQL injection: '; DROP TABLE summaries; --\n"
        "Quotes: \"double\" 'single'\n"
        "Backslashes: \\ \\\\ \\\\\\\n"
        "Newlines and tabs:\n\t\tIndented text"
    )

    summary_id = store.save_summary(  # noqa: F841
        thread_id="special-chars-thread",
        summary_text=special_text,
        compact_up_to_index=50,
        compacted_at=100,
    )

    # Retrieve and verify exact match
    summary = store.get_latest_summary("special-chars-thread")
    assert summary is not None
    assert summary.summary_text == special_text

    # Verify the database still exists (SQL injection didn't work)
    all_summaries = store.list_summaries("special-chars-thread")
    assert len(all_summaries) == 1


def test_negative_indices(temp_db):
    """Test negative, zero, and maxsize indices."""
    store = SummaryStore(temp_db)

    # Test negative index
    _summary_id_neg = store.save_summary(
        thread_id="negative-index-thread",
        summary_text="Negative index test",
        compact_up_to_index=-1,
        compacted_at=-10,
    )

    summary_neg = store.get_latest_summary("negative-index-thread")
    assert summary_neg is not None
    assert summary_neg.compact_up_to_index == -1
    assert summary_neg.compacted_at == -10

    # Test zero index
    _summary_id_zero = store.save_summary(
        thread_id="zero-index-thread",
        summary_text="Zero index test",
        compact_up_to_index=0,
        compacted_at=0,
    )

    summary_zero = store.get_latest_summary("zero-index-thread")
    assert summary_zero is not None
    assert summary_zero.compact_up_to_index == 0
    assert summary_zero.compacted_at == 0

    # Test maxsize index
    _summary_id_max = store.save_summary(
        thread_id="maxsize-index-thread",
        summary_text="Maxsize index test",
        compact_up_to_index=sys.maxsize,
        compacted_at=sys.maxsize,
    )

    summary_max = store.get_latest_summary("maxsize-index-thread")
    assert summary_max is not None
    assert summary_max.compact_up_to_index == sys.maxsize
    assert summary_max.compacted_at == sys.maxsize


def test_empty_summary_text(temp_db):
    """Test empty string summaries."""
    store = SummaryStore(temp_db)

    # Save empty summary
    summary_id = store.save_summary(
        thread_id="empty-summary-thread",
        summary_text="",
        compact_up_to_index=10,
        compacted_at=20,
    )

    assert summary_id.startswith("empty-summary-thread_")

    # Retrieve and verify
    summary = store.get_latest_summary("empty-summary-thread")
    assert summary is not None
    assert summary.summary_text == ""
    assert summary.compact_up_to_index == 10
    assert summary.compacted_at == 20


def test_database_locked_retry(temp_db):
    """Test database lock and retry mechanism."""
    store = SummaryStore(temp_db)

    # Mock the connection to raise OperationalError on first attempt
    original_connect = sqlite3.connect
    call_count = {"count": 0}

    def mock_connect(*args, **kwargs):
        call_count["count"] += 1
        if call_count["count"] == 1:
            # First call raises database locked error
            raise sqlite3.OperationalError("database is locked")
        # Subsequent calls succeed
        return original_connect(*args, **kwargs)

    with patch("sqlite3.connect", side_effect=mock_connect):
        # This should retry and succeed
        summary_id = store.save_summary(
            thread_id="retry-thread",
            summary_text="Retry test",
            compact_up_to_index=5,
            compacted_at=10,
            max_retries=3,
        )

    # Verify it succeeded after retry
    assert summary_id.startswith("retry-thread_")
    assert call_count["count"] == 2  # First failed, second succeeded

    # Verify the summary was saved
    summary = store.get_latest_summary("retry-thread")
    assert summary is not None
    assert summary.summary_text == "Retry test"


def test_transaction_rollback_on_error(temp_db):
    """Test transaction rollback when error occurs during save."""
    store = SummaryStore(temp_db)

    # First, save a valid summary
    store.save_summary(
        thread_id="rollback-thread",
        summary_text="Initial summary",
        compact_up_to_index=10,
        compacted_at=20,
    )

    # Verify it exists
    initial_summaries = store.list_summaries("rollback-thread")
    assert len(initial_summaries) == 1

    # Import the module to patch its _connect function
    from core.runtime.middleware.memory import summary_store

    original_connect = summary_store._connect
    call_count = {"count": 0}

    class MockConnection:
        """Wrapper around sqlite3.Connection that can fail on INSERT."""

        def __init__(self, real_conn):
            self._conn = real_conn

        def execute(self, sql, *args):
            call_count["count"] += 1
            # Fail on the INSERT INTO summaries statement (after deactivation UPDATE)
            if call_count["count"] > 1 and "INSERT INTO summaries" in str(sql):
                raise sqlite3.IntegrityError("Simulated error")
            return self._conn.execute(sql, *args)

        def commit(self):
            return self._conn.commit()

        def rollback(self):
            return self._conn.rollback()

        def close(self):
            return self._conn.close()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
            self.close()
            return False

    def mock_connect(db_path):
        conn = original_connect(db_path)
        return MockConnection(conn)

    with patch.object(summary_store, "_connect", side_effect=mock_connect):
        # This should fail and rollback
        with pytest.raises(sqlite3.IntegrityError):
            store.save_summary(
                thread_id="rollback-thread",
                summary_text="This should fail",
                compact_up_to_index=30,
                compacted_at=40,
                max_retries=1,  # Don't retry to make test faster
            )

    # Verify the original summary is still there and still active
    summaries_after = store.list_summaries("rollback-thread")
    assert len(summaries_after) == 1
    assert summaries_after[0]["compact_up_to_index"] == 10
    assert summaries_after[0]["compacted_at"] == 20
    assert summaries_after[0]["is_active"] == 1  # SQLite stores boolean as integer

    # Also verify using get_latest_summary which includes summary_text
    latest = store.get_latest_summary("rollback-thread")
    assert latest is not None
    assert latest.summary_text == "Initial summary"
    assert latest.is_active is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
