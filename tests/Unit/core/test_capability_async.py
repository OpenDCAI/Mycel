import asyncio
import uuid

from sandbox.capability import SandboxCapability
from sandbox.interfaces.executor import AsyncCommand, ExecuteResult


class _DummyState:
    cwd = "/tmp"


class _DummyTerminal:
    terminal_id = "dummy-term"

    def get_state(self):
        return _DummyState()


class _DummyRuntime:
    def __init__(self):
        self.commands: list[str] = []
        self._async_commands: dict[str, AsyncCommand] = {}

    async def execute(self, command: str, timeout=None):
        self.commands.append(command)
        await asyncio.sleep(0.01)
        return ExecuteResult(exit_code=0, stdout=f"ok:{command}", stderr="")

    async def start_command(self, command: str, cwd: str) -> AsyncCommand:
        command_id = f"cmd_{uuid.uuid4().hex[:12]}"
        result = await self.execute(command)
        async_cmd = AsyncCommand(
            command_id=command_id,
            command_line=command,
            cwd=cwd,
            exit_code=result.exit_code,
            done=True,
            stdout_buffer=[result.stdout],
        )
        self._async_commands[command_id] = async_cmd
        return async_cmd

    async def get_command(self, command_id: str) -> AsyncCommand | None:
        return self._async_commands.get(command_id)

    async def wait_for_command(self, command_id: str, timeout: float | None = None) -> ExecuteResult | None:
        cmd = self._async_commands.get(command_id)
        if cmd is None:
            return None
        return ExecuteResult(
            exit_code=cmd.exit_code or 0,
            stdout="".join(cmd.stdout_buffer),
            stderr="".join(cmd.stderr_buffer),
        )


class _DummySession:
    def __init__(self):
        self.terminal = _DummyTerminal()
        self.runtime = _DummyRuntime()
        self.touches = 0

    def touch(self):
        self.touches += 1


async def _run_async_command_flow():
    session = _DummySession()
    capability = SandboxCapability(session)

    async_cmd = await capability.command.execute_async("echo hi", cwd="/tmp/demo", env={"A": "1"})
    assert async_cmd.command_id.startswith("cmd_")

    status = await capability.command.get_status(async_cmd.command_id)
    assert status is not None

    result = await capability.command.wait_for(async_cmd.command_id, timeout=1.0)
    assert result is not None
    assert result.exit_code == 0
    assert "echo hi" in result.stdout
    assert session.touches > 0


def test_command_wrapper_supports_execute_async():
    asyncio.run(_run_async_command_flow())
