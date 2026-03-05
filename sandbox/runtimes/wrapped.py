"""_RemoteRuntimeBase and RemoteWrappedRuntime — provider execute-based remote runtime."""

from __future__ import annotations

import shlex
import uuid
from typing import TYPE_CHECKING

from sandbox.interfaces.executor import ExecuteResult
from sandbox.runtimes.base import (
    PhysicalTerminalRuntime,
    _extract_state_from_output,
)

if TYPE_CHECKING:
    from sandbox.lease import SandboxLease
    from sandbox.provider import SandboxProvider
    from sandbox.terminal import AbstractTerminal


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
            "no ip address found",
            "is the sandbox started",
            "is paused",
            "stopped",
            "connection",
            # Websocket/PTY transport failures (sandbox may still be started; handle is stale).
            "websocket",
            "close frame",
            "no close frame",
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
        start_marker = f"__LEON_STATE_START_{uuid.uuid4().hex[:8]}__"
        end_marker = f"__LEON_STATE_END_{uuid.uuid4().hex[:8]}__"
        exports = "\n".join(f"export {key}={shlex.quote(value)}" for key, value in state.env_delta.items())
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

        new_cwd, env_map, raw_output = _extract_state_from_output(
            raw_output,
            start_marker,
            end_marker,
            cwd_fallback=state.cwd,
            env_fallback=state.env_delta,
        )
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
