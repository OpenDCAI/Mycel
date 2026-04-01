"""Performance tests for SummaryStore.

This module tests the performance characteristics of SummaryStore operations
to ensure they meet production requirements.

Test Cases:
1. Query performance with many summaries (1000 summaries, query < 50ms)
2. Concurrent write performance (10 threads, avg write < 100ms)
3. Database size growth (100 summaries, DB < 1MB)
"""

import sys
import threading
import time

import pytest

_SKIP_WINDOWS = pytest.mark.skipif(
    sys.platform == "win32", reason="SQLite connection-per-call is slow on Windows; performance tests not meaningful there"
)

from core.runtime.middleware.memory.summary_store import SummaryStore


@_SKIP_WINDOWS
def test_query_performance_with_many_summaries(temp_db):
    """Test query performance with 1000 summaries.

    Requirements:
    - Create 1000 summaries across multiple threads
    - Query for latest summary should complete in < 50ms
    - Index should enable fast lookups even with large dataset
    """
    store = SummaryStore(temp_db)

    # Create 1000 summaries across 100 threads (10 summaries per thread)
    num_threads = 100
    summaries_per_thread = 10

    print(f"\n[Performance Test] Creating {num_threads * summaries_per_thread} summaries...")
    start_time = time.perf_counter()

    for thread_idx in range(num_threads):
        thread_id = f"thread-{thread_idx:04d}"
        for summary_idx in range(summaries_per_thread):
            store.save_summary(
                thread_id=thread_id,
                summary_text=f"Summary {summary_idx} for {thread_id}. " * 10,  # ~500 chars
                compact_up_to_index=summary_idx * 10,
                compacted_at=summary_idx * 20,
            )

    creation_time = time.perf_counter() - start_time
    print(f"[Performance Test] Created 1000 summaries in {creation_time:.2f}s")

    # Now test query performance on a thread with many summaries
    # Query the middle thread to avoid edge cases
    target_thread = "thread-0050"

    # Warm up query (first query might be slower due to cold cache)
    store.get_latest_summary(target_thread)

    # Measure query performance over 10 iterations
    query_times = []
    for _ in range(10):
        start = time.perf_counter()
        summary = store.get_latest_summary(target_thread)
        elapsed = (time.perf_counter() - start) * 1000  # Convert to ms
        query_times.append(elapsed)

        assert summary is not None
        assert summary.thread_id == target_thread

    avg_query_time = sum(query_times) / len(query_times)
    max_query_time = max(query_times)

    print(f"[Performance Test] Query times: avg={avg_query_time:.2f}ms, max={max_query_time:.2f}ms")

    # Assert performance requirements
    assert avg_query_time < 50, f"Average query time {avg_query_time:.2f}ms exceeds 50ms threshold"
    assert max_query_time < 100, f"Max query time {max_query_time:.2f}ms exceeds 100ms threshold"


@_SKIP_WINDOWS
def test_concurrent_write_performance(temp_db):
    """Test concurrent write performance with 10 threads.

    Requirements:
    - 10 threads writing concurrently
    - Each thread writes 10 summaries
    - Average write time per summary < 100ms
    - No database locks or corruption
    """
    store = SummaryStore(temp_db)

    num_threads = 10
    summaries_per_thread = 10

    results = []
    errors = []

    def write_summaries(thread_idx: int):
        """Worker function to write summaries."""
        thread_id = f"concurrent-thread-{thread_idx:02d}"
        thread_times = []

        try:
            for summary_idx in range(summaries_per_thread):
                start = time.perf_counter()

                store.save_summary(
                    thread_id=thread_id,
                    summary_text=f"Concurrent summary {summary_idx} from thread {thread_idx}. " * 10,
                    compact_up_to_index=summary_idx * 10,
                    compacted_at=summary_idx * 20,
                )

                elapsed = (time.perf_counter() - start) * 1000  # Convert to ms
                thread_times.append(elapsed)

            results.append(
                {
                    "thread_idx": thread_idx,
                    "times": thread_times,
                    "avg_time": sum(thread_times) / len(thread_times),
                }
            )
        except Exception as e:
            errors.append(
                {
                    "thread_idx": thread_idx,
                    "error": str(e),
                }
            )

    # Start all threads
    print(f"\n[Performance Test] Starting {num_threads} concurrent write threads...")
    start_time = time.perf_counter()

    threads = []
    for i in range(num_threads):
        t = threading.Thread(target=write_summaries, args=(i,))
        threads.append(t)
        t.start()

    # Wait for all threads to complete
    for t in threads:
        t.join()

    total_time = time.perf_counter() - start_time

    # Check for errors
    assert len(errors) == 0, f"Concurrent writes failed: {errors}"
    assert len(results) == num_threads, f"Expected {num_threads} results, got {len(results)}"

    # Calculate statistics
    all_times = []
    for result in results:
        all_times.extend(result["times"])

    avg_write_time = sum(all_times) / len(all_times)
    max_write_time = max(all_times)
    min_write_time = min(all_times)

    print(f"[Performance Test] Concurrent writes completed in {total_time:.2f}s")
    print(f"[Performance Test] Write times: avg={avg_write_time:.2f}ms, min={min_write_time:.2f}ms, max={max_write_time:.2f}ms")

    # Assert performance requirements
    assert avg_write_time < 100, f"Average write time {avg_write_time:.2f}ms exceeds 100ms threshold"

    # Verify data integrity - each thread should have its latest summary
    for i in range(num_threads):
        thread_id = f"concurrent-thread-{i:02d}"
        summary = store.get_latest_summary(thread_id)
        assert summary is not None, f"Missing summary for {thread_id}"
        assert summary.thread_id == thread_id
        assert summary.compact_up_to_index == (summaries_per_thread - 1) * 10


@_SKIP_WINDOWS
def test_database_size_growth(temp_db):
    """Test database size growth with 100 summaries.

    Requirements:
    - Create 100 summaries with realistic content
    - Database size (including WAL files) should be < 1MB
    - Verify efficient storage without excessive overhead
    """
    store = SummaryStore(temp_db)

    num_summaries = 100

    # Create realistic summary content (~2KB per summary)
    summary_template = (
        """
    The conversation covered the following topics:
    - User requested implementation of feature X
    - Discussion about architecture and design patterns
    - Code review and feedback on proposed changes
    - Testing strategy and coverage requirements
    - Documentation updates and API changes
    """
        * 10
    )  # ~2KB of text

    print(f"\n[Performance Test] Creating {num_summaries} summaries with realistic content...")

    for i in range(num_summaries):
        store.save_summary(
            thread_id=f"size-test-thread-{i:03d}",
            summary_text=f"Summary {i}: {summary_template}",
            compact_up_to_index=i * 10,
            compacted_at=i * 20,
            is_split_turn=(i % 5 == 0),  # 20% split turns
            split_turn_prefix=f"Prefix for summary {i}" if i % 5 == 0 else None,
        )

    # Force WAL checkpoint to flush data to main database
    import sqlite3

    conn = sqlite3.connect(str(temp_db))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()
    finally:
        conn.close()

    # Calculate total database size (main DB + WAL files)
    db_size = temp_db.stat().st_size

    wal_size = 0
    for suffix in ["-wal", "-shm"]:
        wal_file = Path(str(temp_db) + suffix)
        if wal_file.exists():
            wal_size += wal_file.stat().st_size

    total_size = db_size + wal_size
    total_size_kb = total_size / 1024
    total_size_mb = total_size / (1024 * 1024)

    print("[Performance Test] Database sizes:")
    print(f"  - Main DB: {db_size / 1024:.2f} KB")
    print(f"  - WAL files: {wal_size / 1024:.2f} KB")
    print(f"  - Total: {total_size_kb:.2f} KB ({total_size_mb:.3f} MB)")

    # Assert size requirements
    assert total_size < 1024 * 1024, f"Database size {total_size_mb:.3f}MB exceeds 1MB threshold"

    # Verify data integrity - spot check a few summaries
    for i in [0, 49, 99]:
        thread_id = f"size-test-thread-{i:03d}"
        summary = store.get_latest_summary(thread_id)
        assert summary is not None, f"Missing summary for {thread_id}"
        assert summary.thread_id == thread_id
        assert summary.compact_up_to_index == i * 10
        assert summary_template in summary.summary_text

    # Verify total count
    all_threads = [f"size-test-thread-{i:03d}" for i in range(num_summaries)]
    found_count = sum(1 for tid in all_threads if store.get_latest_summary(tid) is not None)
    assert found_count == num_summaries, f"Expected {num_summaries} summaries, found {found_count}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
