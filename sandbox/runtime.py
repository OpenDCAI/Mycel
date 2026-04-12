"""PhysicalTerminalRuntime ABC, helpers, and remote runtime base classes."""

from __future__ import annotations

import asyncio
import os
import platform
import re
import shlex
import sqlite3
import subprocess
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sandbox.lease import SandboxLease
    from sandbox.provider import SandboxProvider
    from sandbox.terminal import AbstractTerminal, TerminalState

from sandbox.interfaces.executor import AsyncCommand, ExecuteResult
from sandbox.shell_output import normalize_pty_result
from storage.providers.sqlite.kernel import SQLiteDBRole, connect_sqlite, resolve_role_db_path
from storage.runtime import uses_supabase_runtime_defaults

if platform.system() == "Windows":
    pty = None
    select = None
else:
    import pty
    import select

ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _uses_strategy_command_registry(db_path: Path | None) -> bool:
    return db_path is not None and uses_supabase_runtime_defaults() and db_path == resolve_role_db_path(SQLiteDBRole.SANDBOX)


def _require_select_module():
    if select is None:
        raise RuntimeError("PTY sessions are not supported on Windows")
    return select


def _parse_env_output(raw: str) -> dict[str, str]:
    env_map: dict[str, str] = {}
    for line in raw.replace("\r", "").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if not ENV_NAME_RE.match(key):
            continue
        env_map[key] = value
    return env_map


def _sanitize_shell_output(raw: str) -> str:
    cleaned = raw.replace("\r", "").replace("\x01\x01\x01", "").replace("\x02\x02\x02", "")
    cleaned = re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", cleaned)
    cleaned = re.sub(r"\x1B\][^\x07]*\x07", "", cleaned)
    while True:
        next_cleaned = re.sub(r"[^\n]\x08", "", cleaned)
        if next_cleaned == cleaned:
            break
        cleaned = next_cleaned
    cleaned = cleaned.replace("\x08", "")
    cleaned = "".join(ch for ch in cleaned if ch in "\n\t" or 32 <= ord(ch))
    return cleaned


def _normalize_pty_result(output: str, command: str | None = None) -> str:
    return normalize_pty_result(output, command)


def _extract_state_from_output(
    raw_output: str,
    start_marker: str,
    end_marker: str,
    *,
    previous_cwd: str,
    previous_env: dict[str, str],
) -> tuple[str, dict[str, str], str]:
    pattern = re.compile(rf"{re.escape(start_marker)}(.*?){re.escape(end_marker)}", re.S)
    matches = list(pattern.finditer(raw_output))
    if not matches:
        # @@@markerless-empty-output-preserve-state - Some lightweight providers/tests return empty stdout on successful exec.
        # Keep previous terminal snapshot only for truly-empty output; any non-empty markerless output still fails loudly.
        if not _sanitize_shell_output(raw_output).strip():
            return previous_cwd, dict(previous_env), ""
        raise RuntimeError("Failed to parse terminal state: state markers not found")

    match = matches[-1]
    pre_state = raw_output[: match.start()]
    state_blob = match.group(1)
    post_state = raw_output[match.end() :]
    state_lines = [_sanitize_shell_output(line).strip() for line in state_blob.splitlines()]
    state_lines = [line for line in state_lines if line]

    new_cwd = ""
    parsed_env: dict[str, str] = {}
    for line in state_lines:
        if "=" in line:
            key, value = line.split("=", 1)
            if ENV_NAME_RE.match(key):
                parsed_env[key] = value
            continue
        if os.path.isabs(line):
            new_cwd = line

    if not new_cwd:
        raise RuntimeError("Failed to parse terminal state: cwd not found in state snapshot")
    if not parsed_env:
        raise RuntimeError("Failed to parse terminal state: env snapshot is empty")

    cleaned_output = _sanitize_shell_output(pre_state + post_state).strip()
    return new_cwd, parsed_env, cleaned_output


def _compute_env_delta(
    env_map: dict[str, str],
    baseline_env: dict[str, str],
    prev_env_delta: dict[str, str],
) -> dict[str, str]:
    persisted_keys = set(prev_env_delta.keys())
    return {k: v for k, v in env_map.items() if baseline_env.get(k) != v or k in persisted_keys}


def _build_export_block(env_delta: dict[str, str]) -> str:
    return "\n".join(f"export {k}={shlex.quote(str(v))}" for k, v in env_delta.items())


def _build_state_snapshot_cmd() -> tuple[str, str, str]:
    """Returns (start_marker, end_marker, full_cmd)."""
    start = f"__LEON_STATE_START_{uuid.uuid4().hex[:8]}__"
    end = f"__LEON_STATE_END_{uuid.uuid4().hex[:8]}__"
    cmd = "\n".join([f"echo {shlex.quote(start)}", "pwd", "env", f"echo {shlex.quote(end)}"])
    return start, end, cmd


def _extract_marker_exit(raw: str, marker: str, command: str | None = None) -> tuple[str, int]:
    exit_code = 0
    cleaned_lines: list[str] = []
    marker_re = re.compile(rf"{re.escape(marker)}\s+(-?\d+)")
    for line in raw.replace("\r", "").splitlines():
        m = marker_re.search(line)
        if m:
            exit_code = int(m.group(1))
            continue
        cleaned_lines.append(line)
    cleaned = _sanitize_shell_output("\n".join(cleaned_lines).strip())
    return _normalize_pty_result(cleaned, command), exit_code


class _SubprocessPtySession:
    def __init__(self, command: list[str], cwd: str | None = None):
        self.command = command
        self.cwd = cwd
        self._master_fd: int | None = None
        self._proc: subprocess.Popen[bytes] | None = None

    @property
    def process(self) -> subprocess.Popen[bytes] | None:
        return self._proc

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        if self.is_alive():
            return
        if pty is None:
            raise RuntimeError("PTY sessions are not supported on Windows")
        master_fd, slave_fd = pty.openpty()
        try:
            self._proc = subprocess.Popen(
                self.command,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=self.cwd,
                close_fds=True,
            )
        finally:
            os.close(slave_fd)
        self._master_fd = master_fd

    def run(
        self,
        command: str,
        timeout: float | None,
        on_stdout_chunk: Callable[[str], None] | None = None,
    ) -> tuple[str, str, int]:
        if not self.is_alive() or self._master_fd is None:
            raise RuntimeError("PTY session is not running")

        marker = f"__LEON_PTY_END_{uuid.uuid4().hex[:8]}__"
        marker_done_re = re.compile(rf"{re.escape(marker)}\s+-?\d+")
        payload = f"{command}\nprintf '\\n{marker} %s\\n' $?\n"
        os.write(self._master_fd, payload.encode("utf-8"))

        raw = bytearray()
        emitted_raw_len = 0
        deadline = time.monotonic() + timeout if timeout else None
        while True:
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError(f"Command timed out after {timeout}s")
            wait_sec = 0.1 if deadline is None else max(0.0, min(0.1, deadline - time.monotonic()))
            readable, _, _ = _require_select_module().select([self._master_fd], [], [], wait_sec)
            if not readable:
                continue
            chunk = os.read(self._master_fd, 4096)
            if not chunk:
                raise RuntimeError("PTY stream closed unexpectedly")
            raw.extend(chunk)
            decoded = raw.decode("utf-8", errors="replace")
            if marker_done_re.search(decoded):
                cleaned, exit_code = _extract_marker_exit(decoded, marker, command)
                return cleaned, "", exit_code
            if on_stdout_chunk is not None:
                if len(decoded) > emitted_raw_len:
                    delta_raw = decoded[emitted_raw_len:]
                    emitted_raw_len = len(decoded)
                    delta = _sanitize_shell_output(delta_raw)
                    if delta:
                        on_stdout_chunk(delta)

    def interrupt_and_recover(self, recover_timeout: float = 3.0) -> bool:
        """Send Ctrl+C to interrupt the current command and recover the session.

        Blocks for up to 1s (drain) + recover_timeout (default 3s) = ~4s worst case.
        Called inside _session_lock, so other commands wait during recovery.

        Returns True if the session is recovered and ready for new commands.
        Returns False if the session is dead and needs to be recreated.
        """
        if not self.is_alive() or self._master_fd is None:
            return False

        # Step 1: Send Ctrl+C (SIGINT) to kill the foreground process
        try:
            os.write(self._master_fd, b"\x03\n")
        except OSError:
            return False

        # Step 2: Drain remaining output until deadline (not just first quiet gap,
        # because bursty processes like rg may have short pauses between output chunks)
        drain_deadline = time.monotonic() + 1.0
        while time.monotonic() < drain_deadline:
            remaining = max(0.0, drain_deadline - time.monotonic())
            readable, _, _ = _require_select_module().select([self._master_fd], [], [], min(0.1, remaining))
            if not readable:
                continue
            try:
                chunk = os.read(self._master_fd, 65536)
                if not chunk:
                    return False
            except OSError:
                return False

        # Step 3: Verify the shell is responsive with a probe command.
        # Use `true &&` to reset $? to 0 (SIGINT leaves $?=130).
        probe_marker = f"__LEON_PROBE_{uuid.uuid4().hex[:8]}__"
        probe_re = re.compile(rf"{re.escape(probe_marker)}\s+0")
        try:
            os.write(self._master_fd, f"true && printf '\\n{probe_marker} %s\\n' $?\n".encode())
        except OSError:
            return False

        probe_deadline = time.monotonic() + recover_timeout
        probe_buf = bytearray()
        while time.monotonic() < probe_deadline:
            wait_sec = max(0.0, min(0.1, probe_deadline - time.monotonic()))
            readable, _, _ = _require_select_module().select([self._master_fd], [], [], wait_sec)
            if not readable:
                continue
            try:
                chunk = os.read(self._master_fd, 4096)
                if not chunk:
                    return False
            except OSError:
                return False
            probe_buf.extend(chunk)
            if probe_re.search(probe_buf.decode("utf-8", errors="replace")):
                return True

        # Probe timed out — shell is unresponsive
        return False

    def close(self) -> None:
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None

        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5.0)
            except Exception:
                self._proc.kill()
                self._proc.wait(timeout=5.0)


class PhysicalTerminalRuntime(ABC):
    """Ephemeral shell/pty process owned by ChatSession.

    This is the actual running process that executes commands.
    It's ephemeral - when the ChatSession ends, this dies.

    Responsibilities:
    - Own physical shell/pty process
    - Execute commands
    - Hydrate state from AbstractTerminal on startup
    - Persist state to AbstractTerminal after commands
    - Provide access to lease for I/O operations

    Does NOT:
    - Own terminal identity (that's AbstractTerminal)
    - Own compute lifecycle (that's SandboxLease)
    - Outlive ChatSession
    """

    def __init__(
        self,
        terminal: AbstractTerminal,
        lease: SandboxLease,
    ):
        self.terminal = terminal
        self.lease = lease
        self.runtime_id = f"runtime-{uuid.uuid4().hex[:12]}"
        self.chat_session_id: str | None = None
        self._commands: dict[str, AsyncCommand] = {}
        self._tasks: dict[str, asyncio.Task[ExecuteResult]] = {}
        self._stream_flush_interval_sec = 0.2
        self._last_stream_flush_at: dict[str, float] = {}
        self._persisted_stdout_chunk_count: dict[str, int] = {}
        self._persisted_stderr_chunk_count: dict[str, int] = {}
        self._chunk_table_available: bool | None = None
        self._running_output_tail_limit = 4096
        self._command_repo = None

    def bind_session(self, session_id: str) -> None:
        self.chat_session_id = session_id

    def bind_command_repo(self, command_repo) -> None:
        self._command_repo = command_repo

    def _require_command_repo(self):
        if self._command_repo is not None:
            return self._command_repo
        db_path = getattr(self.terminal, "db_path", None)
        if db_path and _uses_strategy_command_registry(Path(db_path)):
            raise RuntimeError("strategy-backed terminal command registry requires a bound command repo")
        return None

    def _db_path(self) -> Path:
        db_path = getattr(self.terminal, "db_path", None)
        if not db_path:
            raise RuntimeError("Terminal db_path is required for command registry")
        return Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self._db_path())

    def _has_chunk_table(self, conn: sqlite3.Connection) -> bool:
        cached = self._chunk_table_available
        if cached is not None:
            return cached
        row = conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'terminal_command_chunks'
            LIMIT 1
            """
        ).fetchone()
        self._chunk_table_available = row is not None
        return self._chunk_table_available

    @staticmethod
    def _tail_output(chunks: list[str], *, max_chars: int) -> str:
        if not chunks:
            return ""
        merged = "".join(chunks[-32:])
        if len(merged) <= max_chars:
            return merged
        return merged[-max_chars:]

    def _append_unflushed_chunks(
        self,
        conn: sqlite3.Connection | None,
        *,
        command_id: str,
        async_cmd: AsyncCommand,
    ) -> None:
        stdout_start = self._persisted_stdout_chunk_count.get(command_id, 0)
        stderr_start = self._persisted_stderr_chunk_count.get(command_id, 0)
        stdout_chunks = async_cmd.stdout_buffer[stdout_start:]
        stderr_chunks = async_cmd.stderr_buffer[stderr_start:]
        if not stdout_chunks and not stderr_chunks:
            return
        created_at = datetime.now().isoformat()
        command_repo = self._require_command_repo()
        if command_repo is not None:
            command_repo.append_command_chunks(
                command_id=command_id,
                stdout_chunks=stdout_chunks,
                stderr_chunks=stderr_chunks,
                created_at=created_at,
            )
            if stdout_chunks:
                self._persisted_stdout_chunk_count[command_id] = stdout_start + len(stdout_chunks)
            if stderr_chunks:
                self._persisted_stderr_chunk_count[command_id] = stderr_start + len(stderr_chunks)
            return
        if conn is None or not self._has_chunk_table(conn):
            return
        if stdout_chunks:
            conn.executemany(
                """
                INSERT INTO terminal_command_chunks (command_id, stream, content, created_at)
                VALUES (?, 'stdout', ?, ?)
                """,
                [(command_id, chunk, created_at) for chunk in stdout_chunks],
            )
            self._persisted_stdout_chunk_count[command_id] = stdout_start + len(stdout_chunks)
        if stderr_chunks:
            conn.executemany(
                """
                INSERT INTO terminal_command_chunks (command_id, stream, content, created_at)
                VALUES (?, 'stderr', ?, ?)
                """,
                [(command_id, chunk, created_at) for chunk in stderr_chunks],
            )
            self._persisted_stderr_chunk_count[command_id] = stderr_start + len(stderr_chunks)

    def _upsert_command_row(
        self,
        *,
        command_id: str,
        command_line: str,
        cwd: str,
        status: str,
        stdout: str | None = "",
        stderr: str | None = "",
        exit_code: int | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        now = datetime.now().isoformat()
        finished_at = now if status in {"done", "cancelled", "failed"} else None
        command_repo = self._require_command_repo()
        if command_repo is not None:
            command_repo.upsert_command(
                command_id=command_id,
                terminal_id=self.terminal.terminal_id,
                chat_session_id=self.chat_session_id,
                command_line=command_line,
                cwd=cwd,
                status=status,
                stdout=stdout or "",
                stderr=stderr or "",
                exit_code=exit_code,
                updated_at=now,
                finished_at=finished_at,
                created_at=now,
            )
            return
        should_commit = conn is None
        target = conn or self._connect()
        try:
            existing = target.execute(
                "SELECT command_id, created_at FROM terminal_commands WHERE command_id = ?",
                (command_id,),
            ).fetchone()
            if existing:
                target.execute(
                    """
                    UPDATE terminal_commands
                    SET status = ?,
                        stdout = COALESCE(?, stdout),
                        stderr = COALESCE(?, stderr),
                        exit_code = ?,
                        updated_at = ?,
                        finished_at = CASE WHEN ? IN ('done', 'cancelled', 'failed') THEN ? ELSE finished_at END
                    WHERE command_id = ?
                    """,
                    (status, stdout, stderr, exit_code, now, status, now, command_id),
                )
            else:
                target.execute(
                    """
                    INSERT INTO terminal_commands (
                        command_id, terminal_id, chat_session_id, command_line, cwd, status,
                        stdout, stderr, exit_code, created_at, updated_at, finished_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        command_id,
                        self.terminal.terminal_id,
                        self.chat_session_id,
                        command_line,
                        cwd,
                        status,
                        stdout or "",
                        stderr or "",
                        exit_code,
                        now,
                        now,
                        finished_at,
                    ),
                )
            if should_commit:
                target.commit()
        finally:
            if should_commit:
                target.close()

    def _flush_running_output_if_needed(self, command_id: str, *, force: bool = False) -> None:
        async_cmd = self._commands.get(command_id)
        if async_cmd is None:
            return
        now = time.monotonic()
        last = self._last_stream_flush_at.get(command_id, 0.0)
        if not force and now - last < self._stream_flush_interval_sec:
            return
        self._last_stream_flush_at[command_id] = now
        if self._require_command_repo() is not None:
            self._append_unflushed_chunks(None, command_id=command_id, async_cmd=async_cmd)
            self._upsert_command_row(
                command_id=command_id,
                command_line=async_cmd.command_line,
                cwd=async_cmd.cwd,
                status="running",
                stdout=self._tail_output(async_cmd.stdout_buffer, max_chars=self._running_output_tail_limit),
                stderr=self._tail_output(async_cmd.stderr_buffer, max_chars=self._running_output_tail_limit),
            )
            return
        with self._connect() as conn:
            self._append_unflushed_chunks(conn, command_id=command_id, async_cmd=async_cmd)
            self._upsert_command_row(
                command_id=command_id,
                command_line=async_cmd.command_line,
                cwd=async_cmd.cwd,
                status="running",
                stdout=self._tail_output(async_cmd.stdout_buffer, max_chars=self._running_output_tail_limit),
                stderr=self._tail_output(async_cmd.stderr_buffer, max_chars=self._running_output_tail_limit),
                conn=conn,
            )
            conn.commit()

    def _load_command_from_db(self, command_id: str) -> AsyncCommand | None:
        command_repo = self._require_command_repo()
        if command_repo is not None:
            row = command_repo.get_command(command_id=command_id, terminal_id=self.terminal.terminal_id)
            stdout_text = ""
            stderr_text = ""
            if row:
                stdout_text = str(row.get("stdout") or "")
                stderr_text = str(row.get("stderr") or "")
                chunk_rows = command_repo.list_command_chunks(command_id=command_id)
                if chunk_rows:
                    stdout_chunks = [str(chunk.get("content") or "") for chunk in chunk_rows if chunk.get("stream") == "stdout"]
                    stderr_chunks = [str(chunk.get("content") or "") for chunk in chunk_rows if chunk.get("stream") == "stderr"]
                    chunk_stdout = "".join(stdout_chunks)
                    chunk_stderr = "".join(stderr_chunks)
                    if row["status"] in {"done", "cancelled", "failed"}:
                        if len(chunk_stdout) >= len(stdout_text):
                            stdout_text = chunk_stdout
                        if len(chunk_stderr) >= len(stderr_text):
                            stderr_text = chunk_stderr
                    else:
                        stdout_text = chunk_stdout
                        stderr_text = chunk_stderr
            if not row:
                return None
            async_cmd = AsyncCommand(
                command_id=row["command_id"],
                command_line=row["command_line"],
                cwd=row["cwd"],
                stdout_buffer=[stdout_text],
                stderr_buffer=[stderr_text],
                exit_code=row["exit_code"],
                done=row["status"] in {"done", "cancelled", "failed"},
            )
            self._commands[command_id] = async_cmd
            return async_cmd
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT command_id, command_line, cwd, status, stdout, stderr, exit_code
                FROM terminal_commands
                WHERE command_id = ? AND terminal_id = ?
                """,
                (command_id, self.terminal.terminal_id),
            ).fetchone()
            stdout_text = ""
            stderr_text = ""
            if row:
                stdout_text = str(row["stdout"] or "")
                stderr_text = str(row["stderr"] or "")
            if row and self._has_chunk_table(conn):
                chunk_rows = conn.execute(
                    """
                    SELECT stream, content
                    FROM terminal_command_chunks
                    WHERE command_id = ?
                    ORDER BY chunk_id ASC
                    """,
                    (command_id,),
                ).fetchall()
                if chunk_rows:
                    stdout_chunks = [str(chunk["content"] or "") for chunk in chunk_rows if chunk["stream"] == "stdout"]
                    stderr_chunks = [str(chunk["content"] or "") for chunk in chunk_rows if chunk["stream"] == "stderr"]
                    chunk_stdout = "".join(stdout_chunks)
                    chunk_stderr = "".join(stderr_chunks)
                    if row["status"] in {"done", "cancelled", "failed"}:
                        if len(chunk_stdout) >= len(stdout_text):
                            stdout_text = chunk_stdout
                        if len(chunk_stderr) >= len(stderr_text):
                            stderr_text = chunk_stderr
                    else:
                        stdout_text = chunk_stdout
                        stderr_text = chunk_stderr
        if not row:
            return None
        async_cmd = AsyncCommand(
            command_id=row["command_id"],
            command_line=row["command_line"],
            cwd=row["cwd"],
            stdout_buffer=[stdout_text],
            stderr_buffer=[stderr_text],
            exit_code=row["exit_code"],
            done=row["status"] in {"done", "cancelled", "failed"},
        )
        self._commands[command_id] = async_cmd
        return async_cmd

    async def start_command(self, command: str, cwd: str) -> AsyncCommand:
        command_id = f"cmd_{uuid.uuid4().hex[:12]}"
        async_cmd = AsyncCommand(
            command_id=command_id,
            command_line=command,
            cwd=cwd,
        )
        self._commands[command_id] = async_cmd
        self._persisted_stdout_chunk_count[command_id] = 0
        self._persisted_stderr_chunk_count[command_id] = 0
        self._upsert_command_row(
            command_id=command_id,
            command_line=command,
            cwd=cwd,
            status="running",
        )

        async def _run() -> ExecuteResult:
            def _append_stdout(chunk: str) -> None:
                if chunk:
                    async_cmd.stdout_buffer.append(chunk)
                    self._flush_running_output_if_needed(command_id)

            try:
                result = await self._execute_background_command(command, timeout=None, on_stdout_chunk=_append_stdout)
                status = "done"
            except Exception as exc:
                result = ExecuteResult(exit_code=1, stdout="", stderr=f"Error: {exc}")
                status = "failed"
            # @@@cancelled-terminal-truth - Runtime-level cancel may tear down the active PTY/session from another task.
            # When that happens, this background runner must not overwrite the authoritative cancelled state with a late
            # success/failure finalizer.
            if async_cmd.cancelled:
                self._last_stream_flush_at.pop(command_id, None)
                self._persisted_stdout_chunk_count.pop(command_id, None)
                self._persisted_stderr_chunk_count.pop(command_id, None)
                return ExecuteResult(
                    exit_code=130,
                    stdout="".join(async_cmd.stdout_buffer),
                    stderr="Command cancelled",
                    command_id=command_id,
                )
            self._flush_running_output_if_needed(command_id, force=True)
            async_cmd.stdout_buffer = [result.stdout]
            async_cmd.stderr_buffer = [result.stderr]
            async_cmd.exit_code = result.exit_code
            async_cmd.done = True
            self._upsert_command_row(
                command_id=command_id,
                command_line=command,
                cwd=cwd,
                status=status,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
            )
            self._last_stream_flush_at.pop(command_id, None)
            self._persisted_stdout_chunk_count.pop(command_id, None)
            self._persisted_stderr_chunk_count.pop(command_id, None)
            return result

        self._tasks[command_id] = asyncio.create_task(_run())
        return async_cmd

    async def _cancel_running_command(self) -> bool:
        return False

    async def _execute_background_command(
        self,
        command: str,
        timeout: float | None,
        on_stdout_chunk: Callable[[str], None] | None = None,
    ) -> ExecuteResult:
        return await self.execute(command, timeout=timeout)

    async def get_command(self, command_id: str) -> AsyncCommand | None:
        cmd = self._commands.get(command_id)
        if cmd:
            if not cmd.done and command_id not in self._tasks:
                # @@@cross-runtime-status-source - If this runtime didn't start the task, trust DB row instead of stale memory.
                refreshed = self._load_command_from_db(command_id)
                return refreshed or cmd
            return cmd
        return self._load_command_from_db(command_id)

    async def wait_for_command(self, command_id: str, timeout: float | None = None) -> ExecuteResult | None:
        async_cmd = await self.get_command(command_id)
        if async_cmd is None:
            return None
        task = self._tasks.get(command_id)
        if task is None and not async_cmd.done:
            deadline = time.monotonic() + timeout if timeout is not None else None
            while not async_cmd.done:
                if deadline is not None and time.monotonic() > deadline:
                    return ExecuteResult(
                        exit_code=-1,
                        stdout="".join(async_cmd.stdout_buffer),
                        stderr="".join(async_cmd.stderr_buffer),
                        timed_out=True,
                        command_id=command_id,
                    )
                await asyncio.sleep(0.1)
                refreshed = self._load_command_from_db(command_id)
                if refreshed is None:
                    return None
                async_cmd = refreshed
        if task is not None and not task.done():
            try:
                if timeout is None:
                    await task
                else:
                    await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
            except TimeoutError:
                return ExecuteResult(
                    exit_code=-1,
                    stdout="".join(async_cmd.stdout_buffer),
                    stderr="".join(async_cmd.stderr_buffer),
                    timed_out=True,
                    command_id=command_id,
                )
            except asyncio.CancelledError:
                return ExecuteResult(
                    exit_code=130,
                    stdout="".join(async_cmd.stdout_buffer),
                    stderr="Command cancelled",
                    command_id=command_id,
                )
        return ExecuteResult(
            exit_code=async_cmd.exit_code or 0,
            stdout="".join(async_cmd.stdout_buffer),
            stderr="".join(async_cmd.stderr_buffer),
            command_id=command_id,
        )

    async def cancel_command(self, command_id: str) -> bool:
        task = self._tasks.get(command_id)
        cmd = await self.get_command(command_id)
        if not task or not cmd:
            return False
        if task.done():
            return False
        # @@@runtime-owned-cancel - Async task cancellation is not sufficient for PTY/session runtimes.
        # The runtime must stop the live command source, then this method records the single terminal truth.
        cmd.cancelled = True
        stopped = await self._cancel_running_command()
        if stopped:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
            except (TimeoutError, asyncio.CancelledError):
                task.cancel()
        else:
            task.cancel()
        cmd.done = True
        cmd.exit_code = 130
        cmd.stderr_buffer = ["Command cancelled"]
        self._upsert_command_row(
            command_id=command_id,
            command_line=cmd.command_line,
            cwd=cmd.cwd,
            status="cancelled",
            stdout="".join(cmd.stdout_buffer),
            stderr="Command cancelled",
            exit_code=130,
        )
        self._last_stream_flush_at.pop(command_id, None)
        self._persisted_stdout_chunk_count.pop(command_id, None)
        self._persisted_stderr_chunk_count.pop(command_id, None)
        return True

    @abstractmethod
    async def execute(self, command: str, timeout: float | None = None) -> ExecuteResult:
        """Execute command in this runtime."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the physical runtime process."""
        ...

    def get_terminal_state(self) -> TerminalState:
        """Get current terminal state."""
        return self.terminal.get_state()

    def update_terminal_state(self, state: TerminalState) -> None:
        """Update terminal state after command execution."""
        self.terminal.update_state(state)


class _RemoteRuntimeBase(PhysicalTerminalRuntime):
    def __init__(
        self,
        terminal: AbstractTerminal,
        lease: SandboxLease,
        provider: SandboxProvider,
    ):
        super().__init__(terminal, lease)
        self.provider = provider

    @staticmethod
    def _looks_like_infra_error(text: str) -> bool:
        message = text.lower()
        markers = (
            "not found",
            "no such session",
            "session does not exist",
            "failed to create pty session",
            "failed to send input to pty",
            "pty control error",
            "no ip address found",
            "is the sandbox started",
            "is paused",
            "stopped",
            "connection",
            # Websocket/PTY transport failures (sandbox may still be started; handle is stale).
            "websocket",
            "close frame",
            "no close frame",
            "internal error",
            "1011",
            "broken pipe",
            "transport",
            "unreachable",
            "timed out",
            "timeout",
            "detached",
            "not running",
        )
        return any(marker in message for marker in markers)

    def _recover_infra(self) -> None:
        # @@@infra-recovery - Refresh provider truth once, then resume/recreate and retry command exactly once.
        status = self.lease.refresh_instance_status(self.provider, force=True, max_age_sec=0)
        if status == "paused":
            if not self.lease.resume_instance(self.provider):
                raise RuntimeError(f"Failed to resume paused lease {self.lease.lease_id}")
            return
        if status in {"detached", "unknown"}:
            self.lease.ensure_active_instance(self.provider)

    def _provider_sandbox(self, instance_id: str):
        getter = getattr(self.provider, "get_runtime_sandbox", None)
        if callable(getter):
            return getter(instance_id)
        private_getter = getattr(self.provider, "_get_sandbox", None)
        if callable(private_getter):
            return private_getter(instance_id)
        raise RuntimeError(f"Provider {getattr(self.provider, 'name', '?')} does not expose runtime sandbox handle")


class RemoteWrappedRuntime(_RemoteRuntimeBase):
    """Remote runtime that wraps provider execute calls.

    For remote providers (E2B, AgentBay, etc), there's no local process.
    Instead, we wrap the provider's execute() and track state via markers.
    """

    def __init__(
        self,
        terminal: AbstractTerminal,
        lease: SandboxLease,
        provider: SandboxProvider,
    ):
        super().__init__(terminal, lease, provider)

    def _execute_once(self, command: str, timeout: float | None = None) -> ExecuteResult:
        instance = self.lease.ensure_active_instance(self.provider)
        state = self.terminal.get_state()
        timeout_ms = int(timeout * 1000) if timeout else 30000
        print(
            "[RemoteWrappedRuntime._execute_once] "
            f"thread_id={self.terminal.thread_id} "
            f"lease_id={self.lease.lease_id} "
            f"instance_id={instance.instance_id} "
            f"provider={getattr(self.provider, 'name', '?')} "
            f"cwd={state.cwd!r} "
            f"timeout_ms={timeout_ms} "
            f"command={command[:200]!r}",
            flush=True,
        )
        # @@@ _build_state_snapshot_cmd returns (start, end, cmd) but RemoteWrappedRuntime
        # builds its own inline block to interleave cd/exports/command, so the pre-built cmd is unused.
        start_marker, end_marker, _ = _build_state_snapshot_cmd()
        exports = _build_export_block(state.env_delta)
        wrapped = "\n".join(
            part
            for part in [
                f"cd {shlex.quote(state.cwd)} || exit 1",
                exports,
                command,
                "__leon_exit_code=$?",
                f"echo {shlex.quote(start_marker)}",
                "pwd",
                "env",
                f"echo {shlex.quote(end_marker)}",
                "exit $__leon_exit_code",
            ]
            if part
        )
        result = self.provider.execute(
            instance.instance_id,
            wrapped,
            timeout_ms=timeout_ms,
            cwd=state.cwd,
        )
        raw_output = result.output or ""
        print(
            "[RemoteWrappedRuntime._execute_once] "
            f"thread_id={self.terminal.thread_id} "
            f"provider_exit={result.exit_code} "
            f"provider_error={result.error!r} "
            f"output_len={len(raw_output)}",
            flush=True,
        )

        try:
            new_cwd, env_map, raw_output = _extract_state_from_output(
                raw_output,
                start_marker,
                end_marker,
                previous_cwd=state.cwd,
                previous_env=state.env_delta,
            )
        except Exception as exc:
            print(
                "[RemoteWrappedRuntime._execute_once] "
                f"thread_id={self.terminal.thread_id} "
                f"state_parse_failed={exc.__class__.__name__}: {exc} "
                f"raw_output_preview={raw_output[:400]!r}",
                flush=True,
            )
            raise
        from sandbox.terminal import TerminalState

        self.update_terminal_state(TerminalState(cwd=new_cwd, env_delta=env_map))

        exit_code = result.exit_code
        if result.error and exit_code == 0:
            exit_code = 1

        return ExecuteResult(
            exit_code=exit_code,
            stdout=raw_output,
            stderr=result.error or "",
        )

    async def execute(self, command: str, timeout: float | None = None) -> ExecuteResult:
        """Execute command via provider."""
        try:
            first = self._execute_once(command, timeout)
        except Exception as e:
            if not self._looks_like_infra_error(str(e)):
                raise
            self._recover_infra()
            return self._execute_once(command, timeout)

        if first.exit_code != 0 and self._looks_like_infra_error(first.stderr or first.stdout):
            self._recover_infra()
            return self._execute_once(command, timeout)

        return first

    async def close(self) -> None:
        """No-op for remote runtime - instance lifecycle managed by lease."""
        pass
