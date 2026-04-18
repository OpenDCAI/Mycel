from types import SimpleNamespace
from typing import Any, cast

import pytest

from sandbox import base as sandbox_base
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
    capability = cast(Any, SimpleNamespace(command=command))
    sandbox = RemoteSandbox.__new__(RemoteSandbox)
    sandbox._config = SandboxConfig(init_commands=["echo init"])

    def _unexpected_threadsafe(*args, **kwargs):
        raise AssertionError("same-loop run_coroutine_threadsafe path should not be used")

    monkeypatch.setattr("sandbox.base.asyncio.run_coroutine_threadsafe", _unexpected_threadsafe)

    sandbox._run_init_commands(capability)

    assert command.calls == ["echo init"]


def test_coroutine_blocking_failure_uses_helper_thread_wording(monkeypatch: pytest.MonkeyPatch):
    async def _noop():
        return "unreachable"

    class _EmptyThread:
        def __init__(self, *, target, daemon):
            self._target = target
            self.daemon = daemon

        def start(self) -> None:
            return None

    class _AlreadyDoneEvent:
        def set(self) -> None:
            return None

        def wait(self, timeout) -> bool:
            return True

    monkeypatch.setattr(sandbox_base.threading, "Thread", _EmptyThread)
    monkeypatch.setattr(sandbox_base.threading, "Event", _AlreadyDoneEvent)
    monkeypatch.setattr(sandbox_base.asyncio, "get_running_loop", lambda: object())

    coro = _noop()
    with pytest.raises(RuntimeError) as exc_info:
        sandbox_base._run_coroutine_blocking(coro, timeout=0.01)
    coro.close()

    assert "helper thread" in str(exc_info.value)
    assert "bridge" not in str(exc_info.value)
