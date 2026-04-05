"""Tests for local sandbox using ChatSession architecture."""

from __future__ import annotations

from pathlib import Path

import pytest

from sandbox.base import LocalSandbox
from sandbox.providers.local import LocalSessionProvider
from sandbox.manager import lookup_sandbox_for_thread
from sandbox.thread_context import set_current_thread_id


@pytest.mark.asyncio
async def test_local_chat_session_persistence_and_resume(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "sandbox.db"

    thread_id = "local-thread-1"
    sandbox = LocalSandbox(workspace_root=str(workspace), db_path=db_path)
    set_current_thread_id(thread_id)
    sandbox.ensure_session(thread_id)

    shell = sandbox.shell()

    first = await shell.execute("cd /tmp && export LEON_LOCAL_VAR=chat-session-ok && pwd")
    assert first.exit_code == 0
    assert "/tmp" in first.stdout

    second = await shell.execute("pwd")
    assert second.exit_code == 0
    assert "/tmp" in second.stdout

    third = await shell.execute("echo $LEON_LOCAL_VAR")
    assert third.exit_code == 0
    assert "chat-session-ok" in third.stdout

    assert sandbox.pause_thread(thread_id)
    assert lookup_sandbox_for_thread(thread_id, db_path=db_path) == "local"
    assert sandbox.resume_thread(thread_id)

    set_current_thread_id(thread_id)
    resumed_pwd = await shell.execute("pwd")
    assert resumed_pwd.exit_code == 0
    assert "/tmp" in resumed_pwd.stdout

    resumed_env = await shell.execute("echo $LEON_LOCAL_VAR")
    assert resumed_env.exit_code == 0
    assert "chat-session-ok" in resumed_env.stdout

    sandbox.close()


def test_local_provider_pause_resume_state_recovery():
    provider = LocalSessionProvider()
    session = provider.create_session(context_id="leon-lease-test-session")
    sid = session.session_id
    provider._session_states.clear()
    assert provider.pause_session(sid)
    assert provider.get_session_status(sid) == "paused"

    provider._session_states.clear()
    assert provider.resume_session(sid)
    assert provider.get_session_status(sid) == "running"
    assert not provider.pause_session("unknown-session-id")
