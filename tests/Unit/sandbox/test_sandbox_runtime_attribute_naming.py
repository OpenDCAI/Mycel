from __future__ import annotations

from pathlib import Path

from sandbox.chat_session import ChatSession, ChatSessionPolicy
from sandbox.providers.local import LocalPersistentShellRuntime
from sandbox.runtime_handle import SandboxInstance, SQLiteSandboxRuntimeHandle
from sandbox.terminal import SQLiteTerminal, TerminalState


def _sandbox_runtime(db_path: Path) -> SQLiteSandboxRuntimeHandle:
    return SQLiteSandboxRuntimeHandle(
        sandbox_runtime_id="runtime-1",
        provider_name="local",
        current_instance=SandboxInstance(
            instance_id="inst-1",
            provider_name="local",
            status="running",
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        ),
        db_path=db_path,
        observed_state="running",
        status="active",
    )


def _terminal(db_path: Path) -> SQLiteTerminal:
    return SQLiteTerminal(
        terminal_id="term-1",
        thread_id="thread-1",
        sandbox_runtime_id="runtime-1",
        state=TerminalState(cwd="/tmp"),
        db_path=db_path,
    )


def test_chat_session_uses_sandbox_runtime_attribute(tmp_path: Path) -> None:
    db_path = tmp_path / "sandbox.db"
    terminal = _terminal(db_path)
    sandbox_runtime = _sandbox_runtime(db_path)
    runtime = LocalPersistentShellRuntime(terminal, sandbox_runtime)
    session = ChatSession(
        session_id="sess-1",
        thread_id="thread-1",
        terminal=terminal,
        sandbox_runtime=sandbox_runtime,
        runtime=runtime,
        policy=ChatSessionPolicy(),
        started_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        last_active_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        db_path=db_path,
    )

    assert session.sandbox_runtime is sandbox_runtime
    assert not hasattr(session, "lea" "se")
    assert terminal.sandbox_runtime_id == "runtime-1"
    assert not hasattr(terminal, "lea" "se_id")
    assert session.sandbox_runtime.sandbox_runtime_id == "runtime-1"
    assert not hasattr(session.sandbox_runtime, "lea" "se_id")


def test_runtime_uses_sandbox_runtime_attribute(tmp_path: Path) -> None:
    db_path = tmp_path / "sandbox.db"
    terminal = _terminal(db_path)
    sandbox_runtime = _sandbox_runtime(db_path)
    runtime = LocalPersistentShellRuntime(terminal, sandbox_runtime)

    assert terminal.sandbox_runtime_id == "runtime-1"
    assert not hasattr(terminal, "lea" "se_id")
    assert runtime.sandbox_runtime is sandbox_runtime
    assert not hasattr(runtime, "lea" "se")
    assert runtime.sandbox_runtime.sandbox_runtime_id == "runtime-1"
    assert not hasattr(runtime.sandbox_runtime, "lea" "se_id")
