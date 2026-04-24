import asyncio
import shutil
import sys

import pytest

from core.tools.command.bash.executor import BashExecutor
from core.tools.command.zsh.executor import ZshExecutor


@pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None, reason="bash persistence tests require a Unix shell")
def test_bash_env_persistence():
    async def run():
        executor = BashExecutor()

        result1 = await executor.execute("export TEST_VAR=hello")
        assert result1.exit_code == 0

        result2 = await executor.execute("echo $TEST_VAR")
        assert result2.exit_code == 0
        assert "hello" in result2.stdout

    asyncio.run(run())


@pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None, reason="bash persistence tests require a Unix shell")
def test_bash_cwd_persistence():
    async def run():
        executor = BashExecutor()

        result1 = await executor.execute("mkdir -p /tmp/test_leon_bash && cd /tmp/test_leon_bash && pwd")
        assert result1.exit_code == 0
        assert "/tmp/test_leon_bash" in result1.stdout

        result2 = await executor.execute("pwd")
        assert result2.exit_code == 0
        assert "/tmp/test_leon_bash" in result2.stdout

        await executor.execute("cd /tmp && rm -rf /tmp/test_leon_bash")

    asyncio.run(run())


@pytest.mark.skipif(sys.platform == "win32" or shutil.which("zsh") is None, reason="zsh persistence tests require a Unix shell")
def test_zsh_env_persistence():
    async def run():
        executor = ZshExecutor()

        result1 = await executor.execute("export TEST_VAR=world")
        assert result1.exit_code == 0

        result2 = await executor.execute("echo $TEST_VAR")
        assert result2.exit_code == 0
        assert "world" in result2.stdout

    asyncio.run(run())


@pytest.mark.skipif(sys.platform == "win32" or shutil.which("zsh") is None, reason="zsh persistence tests require a Unix shell")
def test_zsh_cwd_persistence():
    async def run():
        executor = ZshExecutor()

        result1 = await executor.execute("mkdir -p /tmp/test_leon_zsh && cd /tmp/test_leon_zsh && pwd")
        assert result1.exit_code == 0
        assert "/tmp/test_leon_zsh" in result1.stdout

        result2 = await executor.execute("pwd")
        assert result2.exit_code == 0
        assert "/tmp/test_leon_zsh" in result2.stdout

        await executor.execute("cd /tmp && rm -rf /tmp/test_leon_zsh")

    asyncio.run(run())
