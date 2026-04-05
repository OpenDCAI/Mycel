"""Tests for terminal persistence (env/cwd across commands)."""

import asyncio
import shutil
import sys

import pytest

from core.tools.command.bash.executor import BashExecutor
from core.tools.command.zsh.executor import ZshExecutor


# TODO(windows-compat): BashExecutor/ZshExecutor require Unix shell semantics.
# Tracked in: https://github.com/OpenDCAI/Mycel/issues — Windows shell support needed.
@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="bash not available or not Unix-compatible on this platform",
)
def test_bash_env_persistence():
    """Test that environment variables persist across commands in bash."""

    async def run():
        executor = BashExecutor()

        # Set environment variable
        result1 = await executor.execute("export TEST_VAR=hello")
        assert result1.exit_code == 0

        # Check it persists
        result2 = await executor.execute("echo $TEST_VAR")
        assert result2.exit_code == 0
        assert "hello" in result2.stdout

    asyncio.run(run())


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="bash not available or not Unix-compatible on this platform",
)
def test_bash_cwd_persistence():
    """Test that working directory persists across commands in bash."""

    async def run():
        executor = BashExecutor()

        # Create and change to test directory
        result1 = await executor.execute("mkdir -p /tmp/test_leon_bash && cd /tmp/test_leon_bash && pwd")
        assert result1.exit_code == 0
        assert "/tmp/test_leon_bash" in result1.stdout

        # Check we're still in that directory
        result2 = await executor.execute("pwd")
        assert result2.exit_code == 0
        assert "/tmp/test_leon_bash" in result2.stdout

        # Cleanup
        await executor.execute("cd /tmp && rm -rf /tmp/test_leon_bash")

    asyncio.run(run())


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("zsh") is None,
    reason="zsh not available or not Unix-compatible on this platform",
)
def test_zsh_env_persistence():
    """Test that environment variables persist across commands in zsh."""

    async def run():
        executor = ZshExecutor()

        # Set environment variable
        result1 = await executor.execute("export TEST_VAR=world")
        assert result1.exit_code == 0

        # Check it persists
        result2 = await executor.execute("echo $TEST_VAR")
        assert result2.exit_code == 0
        assert "world" in result2.stdout

    asyncio.run(run())


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("zsh") is None,
    reason="zsh not available or not Unix-compatible on this platform",
)
def test_zsh_cwd_persistence():
    """Test that working directory persists across commands in zsh."""

    async def run():
        executor = ZshExecutor()

        # Create and change to test directory
        result1 = await executor.execute("mkdir -p /tmp/test_leon_zsh && cd /tmp/test_leon_zsh && pwd")
        assert result1.exit_code == 0
        assert "/tmp/test_leon_zsh" in result1.stdout

        # Check we're still in that directory
        result2 = await executor.execute("pwd")
        assert result2.exit_code == 0
        assert "/tmp/test_leon_zsh" in result2.stdout

        # Cleanup
        await executor.execute("cd /tmp && rm -rf /tmp/test_leon_zsh")

    asyncio.run(run())
