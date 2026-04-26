import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("LEON_E2E_AGENT"),
    reason="LEON_E2E_AGENT not set (requires working LLM API key for real agent calls)",
)

from core.runtime.agent import create_leon_agent
from core.runtime.middleware.memory.summary_store import SummaryStore
from sandbox.thread_context import set_current_thread_id


def _memory_middleware(agent):
    middleware = getattr(agent, "_memory_middleware", None)
    assert middleware is not None, "summary persistence E2E requires memory middleware"
    return middleware


@pytest.fixture
def test_db_path(tmp_path):
    db_path = tmp_path / "test_e2e_summary.db"
    return str(db_path)


@pytest.fixture
def temp_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return str(workspace)


class TestFullAgentSummaryPersistence:
    def test_full_agent_summary_persistence(self, test_db_path, temp_workspace):
        thread_id = "test-full-lifecycle"
        set_current_thread_id(thread_id)

        agent = create_leon_agent(
            workspace_root=temp_workspace,
            sandbox="local",
        )

        try:
            memory = _memory_middleware(agent)
            memory.summary_store = SummaryStore(Path(test_db_path))
            memory._compaction_threshold = 0.01
            memory.compactor.keep_recent_tokens = 500

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
            )

            result = agent.invoke(large_message, thread_id=thread_id)
            assert result is not None
            assert "messages" in result

            memory = _memory_middleware(agent)
            store = memory.summary_store

            summary = store.get_latest_summary(thread_id)

            assert summary is not None, "Summary should exist after exceeding threshold"
            assert summary.thread_id == thread_id
            assert summary.summary_text is not None
            assert len(summary.summary_text) > 0
            assert summary.compact_up_to_index >= 0

        finally:
            agent.close()

        agent2 = create_leon_agent(
            workspace_root=temp_workspace,
            sandbox="local",
        )

        try:
            memory2 = _memory_middleware(agent2)
            memory2.summary_store = SummaryStore(Path(test_db_path))

            result = agent2.invoke(
                "What files did we create earlier?",
                thread_id=thread_id,
            )

            assert result is not None
            assert "messages" in result

            assert memory2._cached_summary is not None, "Summary should be restored"
            assert memory2._compact_up_to_index >= 0

        finally:
            agent2.close()


class TestAgentSplitTurnE2E:
    def test_agent_split_turn_e2e(self, test_db_path, temp_workspace):
        thread_id = "test-split-turn"
        set_current_thread_id(thread_id)

        agent = create_leon_agent(
            workspace_root=temp_workspace,
            sandbox="local",
        )

        try:
            memory = _memory_middleware(agent)
            memory.summary_store = SummaryStore(Path(test_db_path))
            memory._compaction_threshold = 0.01
            memory.compactor.keep_recent_tokens = 500

            large_content = "x" * 50000  # 50KB of content
            large_message = f"Create a file with this content: {large_content}"

            result = agent.invoke(large_message, thread_id=thread_id)
            assert result is not None

            store = memory.summary_store
            summary = store.get_latest_summary(thread_id)

            if summary and summary.is_split_turn:
                assert summary.split_turn_prefix is not None
                assert len(summary.split_turn_prefix) > 0

        finally:
            agent.close()


class TestAgentConcurrentThreads:
    def test_agent_concurrent_threads(self, test_db_path, temp_workspace):
        thread_ids = ["test-thread-1", "test-thread-2", "test-thread-3"]

        for thread_id in thread_ids:
            set_current_thread_id(thread_id)
            agent = create_leon_agent(
                workspace_root=temp_workspace,
                sandbox="local",
            )

            try:
                memory = _memory_middleware(agent)
                memory.summary_store = SummaryStore(Path(test_db_path))
                memory._compaction_threshold = 0.01

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
                )

                result = agent.invoke(large_message, thread_id=thread_id)
                assert result is not None
            finally:
                agent.close()

        store = SummaryStore(Path(test_db_path))

        for thread_id in thread_ids:
            summary = store.get_latest_summary(thread_id)
            if summary:
                assert summary.thread_id == thread_id

        all_summaries = []
        for thread_id in thread_ids:
            summaries = store.list_summaries(thread_id)
            all_summaries.extend(summaries)

        for summary in all_summaries:
            assert summary["thread_id"] in thread_ids

        for thread_id in thread_ids:
            set_current_thread_id(thread_id)
            agent = create_leon_agent(
                workspace_root=temp_workspace,
                sandbox="local",
            )

            try:
                memory = _memory_middleware(agent)
                memory.summary_store = SummaryStore(Path(test_db_path))

                result = agent.invoke(
                    f"What files did we create in {thread_id}?",
                    thread_id=thread_id,
                )
                assert result is not None

            finally:
                agent.close()
