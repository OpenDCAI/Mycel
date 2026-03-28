from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sandbox.lease import LeaseStore
from sandbox.providers.local import LocalPersistentShellRuntime
from sandbox.terminal import TerminalStore


pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_backend_web_main_imports_on_windows():
    from backend.web.main import app

    assert app.title == "Leon Web Backend"


@pytest.mark.asyncio
async def test_local_runtime_persists_state_on_windows(tmp_path: Path):
    db_path = tmp_path / "sandbox.db"
    terminal_store = TerminalStore(db_path=db_path)
    lease_store = LeaseStore(db_path=db_path)

    terminal = terminal_store.create("term-win", "thread-win", "lease-win", str(tmp_path))
    lease = lease_store.create("lease-win", "local")
    runtime = LocalPersistentShellRuntime(terminal, lease)

    first = await runtime.execute("Set-Location ..; $env:LEON_LOCAL_VAR = 'chat-session-ok'; (Get-Location).Path")
    assert first.exit_code == 0
    assert str(tmp_path.parent) in first.stdout

    second = await runtime.execute("(Get-Location).Path")
    assert second.exit_code == 0
    assert str(tmp_path.parent) in second.stdout

    third = await runtime.execute("Write-Output $env:LEON_LOCAL_VAR")
    assert third.exit_code == 0
    assert "chat-session-ok" in third.stdout

    await runtime.close()
