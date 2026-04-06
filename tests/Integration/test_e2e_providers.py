"""
End-to-end tests with real sandbox providers.

Tests terminal persistence architecture through the agent interface.
Simulates all frontend interactions programmatically.
"""

import asyncio
import os

import pytest

from agent import create_leon_agent
from sandbox import RemoteSandbox
from sandbox.thread_context import set_current_thread_id


@pytest.fixture
def test_db_path(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_e2e.db"
    return str(db_path)


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return str(workspace)


def _require_remote_sandbox(agent) -> RemoteSandbox:
    sandbox = agent.sandbox
    assert isinstance(sandbox, RemoteSandbox)
    return sandbox


def _run_shell(agent, command: str):
    executor = agent.sandbox.shell()
    assert executor is not None
    return asyncio.run(executor.execute(command))


def _read_file(agent, path: str) -> str:
    fs = agent.sandbox.fs()
    assert fs is not None
    return fs.read_file(path).content


def _list_names(agent, path: str) -> list[str]:
    fs = agent.sandbox.fs()
    assert fs is not None
    return [entry.name for entry in fs.list_dir(path).entries]


class TestAgentBayE2E:
    """End-to-end tests with AgentBay provider."""

    @pytest.mark.skipif(not os.getenv("AGENTBAY_API_KEY"), reason="AGENTBAY_API_KEY not set")
    def test_agentbay_basic_execution(self, test_db_path):
        """Test basic command execution through agent with AgentBay."""
        thread_id = "test-agentbay-basic"
        set_current_thread_id(thread_id)

        agent = create_leon_agent(sandbox="agentbay", db_path=test_db_path)

        # Execute command through agent
        result = _run_shell(agent, "echo 'AgentBay Test'")
        assert result.exit_code == 0
        assert "AgentBay Test" in result.stdout

        agent.close()

    @pytest.mark.skipif(not os.getenv("AGENTBAY_API_KEY"), reason="AGENTBAY_API_KEY not set")
    def test_agentbay_terminal_state_persistence(self, test_db_path):
        """Test terminal state persists across commands with AgentBay."""
        thread_id = "test-agentbay-state"
        set_current_thread_id(thread_id)

        agent = create_leon_agent(sandbox="agentbay", db_path=test_db_path)

        # Change directory
        _run_shell(agent, "cd /tmp")
        result = _run_shell(agent, "pwd")
        assert "/tmp" in result.stdout

        # Set environment variable
        _run_shell(agent, "export AGENTBAY_VAR=test123")
        result = _run_shell(agent, "echo $AGENTBAY_VAR")
        assert "test123" in result.stdout

        agent.close()

    @pytest.mark.skipif(not os.getenv("AGENTBAY_API_KEY"), reason="AGENTBAY_API_KEY not set")
    def test_agentbay_file_operations(self, test_db_path):
        """Test file operations with AgentBay."""
        thread_id = "test-agentbay-files"
        set_current_thread_id(thread_id)

        agent = create_leon_agent(sandbox="agentbay", db_path=test_db_path)

        # Create file
        test_content = "AgentBay file test"
        _run_shell(agent, f"echo '{test_content}' > /tmp/agentbay_test.txt")

        # Read file
        content = _read_file(agent, "/tmp/agentbay_test.txt")
        assert test_content in content

        # List directory
        files = _list_names(agent, "/tmp")
        assert "agentbay_test.txt" in files

        agent.close()


@pytest.mark.skipif(not os.getenv("E2B_API_KEY"), reason="E2B_API_KEY not set")
class TestE2BE2E:
    """End-to-end tests with E2B provider."""

    def test_e2b_basic_execution(self, test_db_path):
        """Test basic command execution with E2B."""
        thread_id = "test-e2b-basic"
        set_current_thread_id(thread_id)

        agent = create_leon_agent(sandbox="e2b", db_path=test_db_path)

        result = _run_shell(agent, "echo 'E2B Test'")
        assert result.exit_code == 0
        assert "E2B Test" in result.stdout

        agent.close()

    def test_e2b_terminal_state_persistence(self, test_db_path):
        """Test terminal state persistence with E2B."""
        thread_id = "test-e2b-state"
        set_current_thread_id(thread_id)

        agent = create_leon_agent(sandbox="e2b", db_path=test_db_path)

        # Change directory
        _run_shell(agent, "cd /tmp")
        result = _run_shell(agent, "pwd")
        assert "/tmp" in result.stdout

        # Set env var
        _run_shell(agent, "export E2B_VAR=test123")
        result = _run_shell(agent, "echo $E2B_VAR")
        assert "test123" in result.stdout

        agent.close()

    def test_e2b_file_operations(self, test_db_path):
        """Test file operations with E2B."""
        thread_id = "test-e2b-files"
        set_current_thread_id(thread_id)

        agent = create_leon_agent(sandbox="e2b", db_path=test_db_path)

        # Create file
        test_content = "E2B file test"
        _run_shell(agent, f"echo '{test_content}' > /tmp/e2b_test.txt")

        # Read file
        content = _read_file(agent, "/tmp/e2b_test.txt")
        assert test_content in content

        agent.close()

    def test_e2b_pause_resume(self, test_db_path):
        """Test pause and resume with E2B."""
        thread_id = "test-e2b-pause"
        set_current_thread_id(thread_id)

        agent = create_leon_agent(sandbox="e2b", db_path=test_db_path)

        # Set state
        sandbox = _require_remote_sandbox(agent)
        _run_shell(agent, "cd /tmp")
        _run_shell(agent, "export PAUSE_VAR=preserved")

        # Pause session
        sandbox.manager.pause_session(thread_id)

        # Resume by getting sandbox again
        result = _run_shell(agent, "pwd")
        assert "/tmp" in result.stdout

        result = _run_shell(agent, "echo $PAUSE_VAR")
        assert "preserved" in result.stdout

        agent.close()


@pytest.mark.skipif(not os.getenv("DAYTONA_API_KEY"), reason="DAYTONA_API_KEY not set")
class TestDaytonaE2E:
    """End-to-end tests with Daytona provider."""

    def test_daytona_basic_execution(self, test_db_path):
        """Test basic command execution with Daytona."""
        thread_id = "test-daytona-basic"
        set_current_thread_id(thread_id)

        agent = create_leon_agent(sandbox="daytona", db_path=test_db_path)

        result = _run_shell(agent, "echo 'Daytona Test'")
        assert result.exit_code == 0
        assert "Daytona Test" in result.stdout

        agent.close()

    def test_daytona_terminal_state_persistence(self, test_db_path):
        """Test terminal state persistence with Daytona."""
        thread_id = "test-daytona-state"
        set_current_thread_id(thread_id)

        agent = create_leon_agent(sandbox="daytona", db_path=test_db_path)

        # Change directory
        _run_shell(agent, "cd /tmp")
        result = _run_shell(agent, "pwd")
        assert "/tmp" in result.stdout

        # Set env var
        _run_shell(agent, "export DAYTONA_VAR=test456")
        result = _run_shell(agent, "echo $DAYTONA_VAR")
        assert "test456" in result.stdout

        agent.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
