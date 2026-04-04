from types import SimpleNamespace

import pytest

from sandbox.base import RemoteSandbox
from sandbox.config import SandboxConfig


class _RecordingCommand:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute(self, command: str):
        self.calls.append(command)
        return SimpleNamespace(exit_code=0, stderr="", stdout="")


@pytest.mark.asyncio
async def test_run_init_commands_avoids_same_loop_threadsafe_wait(monkeypatch: pytest.MonkeyPatch):
    command = _RecordingCommand()
    capability = SimpleNamespace(command=command)
    sandbox = RemoteSandbox.__new__(RemoteSandbox)
    sandbox._config = SandboxConfig(init_commands=["echo init"])

    def _unexpected_threadsafe(*args, **kwargs):
        raise AssertionError("same-loop run_coroutine_threadsafe path should not be used")

    monkeypatch.setattr("sandbox.base.asyncio.run_coroutine_threadsafe", _unexpected_threadsafe)

    sandbox._run_init_commands(capability)

    assert command.calls == ["echo init"]
