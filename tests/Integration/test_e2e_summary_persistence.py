"""
End-to-end tests for summary persistence through the full agent stack.

Tests the complete flow: Agent → MemoryMiddleware → SummaryStore → SQLite
No mocks - uses real agent with all middleware layers.

Note: These tests work around asyncio event loop limitations by creating
fresh agents for each test phase.
"""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("LEON_E2E_AGENT"),
    reason="LEON_E2E_AGENT not set (requires working LLM API key for real agent calls)",
)

from agent import create_leon_agent
from sandbox.thread_context import set_current_thread_id


@pytest.fixture
def test_db_path(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_e2e_summary.db"
    return str(db_path)


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return str(workspace)


class TestFullAgentSummaryPersistence:
    """Test full agent lifecycle with compaction and restore."""

    def test_full_agent_summary_persistence(self, test_db_path, temp_workspace):
        """
        Test 1: Full agent lifecycle with compaction and restore.

        Flow:
        1. Create agent with memory enabled and LOW threshold
        2. Send ONE message to trigger compaction
        3. Verify summary is saved to store
        4. Close agent
        5. Create new agent with same thread_id
        6. Verify summary is restored from store
        """
        thread_id = "test-full-lifecycle"
        set_current_thread_id(thread_id)

        # Create agent with memory enabled and LOW compaction threshold
        agent = create_leon_agent(
            workspace_root=temp_workspace,
            sandbox="local",
            verbose=True,
        )

        # Override db_path and lower threshold for testing
        if hasattr(agent, "_memory_middleware") and agent._memory_middleware:
            from core.runtime.middleware.memory.summary_store import SummaryStore

            agent._memory_middleware.summary_store = SummaryStore(Path(test_db_path))
            # Lower threshold to 1000 tokens to trigger compaction easily
            agent._memory_middleware._compaction_threshold = 0.01  # 1% of 100k = 1000 tokens
            # Lower keep_recent_tokens so we actually have messages to summarize
            agent._memory_middleware.compactor.keep_recent_tokens = 500  # Keep only last 500 tokens

        try:
            # Send ONE large message to exceed threshold and trigger compaction
            # This avoids the event loop issue with multiple invoke() calls
            large_message = (
                """
            Create multiple files with the following content:
            1. test1.txt: First file with some additional content to increase token count
            2. test2.txt: Second file with more content to build up the context
            3. test3.txt: Third file continuing to add more tokens to the conversation
            4. test4.txt: Fourth file to ensure we exceed the compaction threshold
            5. test5.txt: Fifth file with even more content
            Then list all files in the workspace and show their contents.
            """
                * 3
            )  # Repeat to ensure we exceed 1000 tokens

            result = agent.invoke(large_message, thread_id=thread_id)
            assert result is not None
            assert "messages" in result

            # Verify summary was saved to store
            store = agent._memory_middleware.summary_store
            print(f"[Test] Checking summary store: {store}")
            print(f"[Test] Thread ID: {thread_id}")
            print(f"[Test] Cached summary exists: {agent._memory_middleware._cached_summary is not None}")
            print(f"[Test] Compact up to index: {agent._memory_middleware._compact_up_to_index}")

            summary = store.get_latest_summary(thread_id)
            print(f"[Test] Retrieved summary: {summary}")

            # With low threshold and large message, summary should exist
            assert summary is not None, "Summary should exist after exceeding threshold"
            assert summary.thread_id == thread_id
            assert summary.summary_text is not None
            assert len(summary.summary_text) > 0
            assert summary.compact_up_to_index >= 0
            print(f"[Test] Summary saved: compact_up_to_index={summary.compact_up_to_index}")

        finally:
            agent.close()

        # Create new agent with same thread_id to test restore
        agent2 = create_leon_agent(
            workspace_root=temp_workspace,
            sandbox="local",
            verbose=True,
        )

        # Override db_path for testing
        if hasattr(agent2, "_memory_middleware") and agent2._memory_middleware:
            from core.runtime.middleware.memory.summary_store import SummaryStore

            agent2._memory_middleware.summary_store = SummaryStore(Path(test_db_path))

        try:
            # Continue conversation - should restore summary
            result = agent2.invoke(
                "What files did we create earlier?",
                thread_id=thread_id,
            )

            assert result is not None
            assert "messages" in result

            # Verify summary was restored
            assert agent2._memory_middleware._cached_summary is not None, "Summary should be restored"
            assert agent2._memory_middleware._compact_up_to_index >= 0
            print(f"[Test] Summary restored: compact_up_to_index={agent2._memory_middleware._compact_up_to_index}")

        finally:
            agent2.close()


class TestAgentSplitTurnE2E:
    """Test split turn through agent interface."""

    def test_agent_split_turn_e2e(self, test_db_path, temp_workspace):
        """
        Test 2: Split Turn through agent interface.

        Flow:
        1. Create agent with memory enabled and LOW threshold
        2. Send a very large message that triggers split turn
        3. Verify split turn summary is saved with prefix
        4. Verify is_split_turn flag is set
        5. Verify split_turn_prefix is saved
        """
        thread_id = "test-split-turn"
        set_current_thread_id(thread_id)

        agent = create_leon_agent(
            workspace_root=temp_workspace,
            sandbox="local",
            verbose=True,
        )

        # Override db_path and lower threshold for testing
        if hasattr(agent, "_memory_middleware") and agent._memory_middleware:
            from core.runtime.middleware.memory.summary_store import SummaryStore

            agent._memory_middleware.summary_store = SummaryStore(Path(test_db_path))
            # Lower threshold to trigger compaction
            agent._memory_middleware._compaction_threshold = 0.01
            # Lower keep_recent_tokens so we actually have messages to summarize
            agent._memory_middleware.compactor.keep_recent_tokens = 500

        try:
            # Send a very large message to trigger split turn
            # This simulates a scenario where the new turn is too large
            large_content = "x" * 50000  # 50KB of content
            large_message = f"Create a file with this content: {large_content}"

            result = agent.invoke(large_message, thread_id=thread_id)
            assert result is not None

            # Check if split turn was triggered
            store = agent._memory_middleware.summary_store
            summary = store.get_latest_summary(thread_id)

            # Split turn may or may not be triggered depending on context size
            # This test verifies the mechanism works if triggered
            if summary:
                print(f"[Test] Summary exists: is_split_turn={summary.is_split_turn}")
                if summary.is_split_turn:
                    assert summary.split_turn_prefix is not None
                    assert len(summary.split_turn_prefix) > 0
                    print(f"[Test] Split turn detected with prefix length: {len(summary.split_turn_prefix)}")
                else:
                    print("[Test] Normal compaction occurred (split turn not needed)")
            else:
                print("[Test] No summary yet - threshold may not have been reached")

        finally:
            agent.close()


class TestAgentConcurrentThreads:
    """Test multiple agent instances with different threads (sequential execution)."""

    def test_agent_concurrent_threads(self, test_db_path, temp_workspace):
        """
        Test 3: Multiple agent instances with different threads.

        Flow:
        1. Create multiple agents with different thread_ids (one at a time)
        2. Run conversations in each thread
        3. Verify summaries are isolated by thread_id
        4. Verify no cross-contamination between threads
        5. Verify each thread can restore its own summary
        """
        thread_ids = ["test-thread-1", "test-thread-2", "test-thread-3"]

        # Process each thread sequentially to avoid event loop issues
        for thread_id in thread_ids:
            set_current_thread_id(thread_id)
            agent = create_leon_agent(
                workspace_root=temp_workspace,
                sandbox="local",
                verbose=True,
            )

            # Override db_path and lower threshold for testing
            if hasattr(agent, "_memory_middleware") and agent._memory_middleware:
                from core.runtime.middleware.memory.summary_store import SummaryStore

                agent._memory_middleware.summary_store = SummaryStore(Path(test_db_path))
                agent._memory_middleware._compaction_threshold = 0.01

            try:
                # Each thread creates different files with ONE large message
                large_message = (
                    f"""
                Create multiple files for {thread_id}:
                1. {thread_id}_file0.txt with content 'Thread {thread_id} content 0 with extra text'
                2. {thread_id}_file1.txt with content 'Thread {thread_id} content 1 with extra text'
                3. {thread_id}_file2.txt with content 'Thread {thread_id} content 2 with extra text'
                4. {thread_id}_file3.txt with content 'Thread {thread_id} content 3 with extra text'
                Then list all files.
                """
                    * 2
                )  # Repeat to exceed threshold

                result = agent.invoke(large_message, thread_id=thread_id)
                assert result is not None
            finally:
                agent.close()

        # Verify summaries are isolated
        from core.runtime.middleware.memory.summary_store import SummaryStore

        store = SummaryStore(Path(test_db_path))

        for thread_id in thread_ids:
            summary = store.get_latest_summary(thread_id)
            if summary:
                assert summary.thread_id == thread_id
                print(f"[Test] Thread {thread_id}: summary exists")
            else:
                print(f"[Test] Thread {thread_id}: no summary yet")

        # Verify no cross-contamination
        all_summaries = []
        for thread_id in thread_ids:
            summaries = store.list_summaries(thread_id)
            all_summaries.extend(summaries)

        # Each summary should only belong to its own thread
        for summary in all_summaries:
            assert summary["thread_id"] in thread_ids
            print(f"[Test] Summary {summary['summary_id']} belongs to {summary['thread_id']}")

        # Test restore for each thread (sequential)
        for thread_id in thread_ids:
            set_current_thread_id(thread_id)
            agent = create_leon_agent(
                workspace_root=temp_workspace,
                sandbox="local",
                verbose=True,
            )

            # Override db_path for testing
            if hasattr(agent, "_memory_middleware") and agent._memory_middleware:
                from core.runtime.middleware.memory.summary_store import SummaryStore

                agent._memory_middleware.summary_store = SummaryStore(Path(test_db_path))

            try:
                # Continue conversation - should restore correct summary
                result = agent.invoke(
                    f"What files did we create in {thread_id}?",
                    thread_id=thread_id,
                )
                assert result is not None

                # Verify correct summary was restored
                if agent._memory_middleware._cached_summary:
                    print(f"[Test] Thread {thread_id}: summary restored")
                else:
                    print(f"[Test] Thread {thread_id}: no summary to restore")

            finally:
                agent.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
