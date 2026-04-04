"""
AgentBay sandbox provider.

Implements SandboxProvider using Alibaba Cloud's AgentBay SDK.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from sandbox.provider import (
    Metrics,
    ProviderCapability,
    ProviderExecResult,
    SandboxProvider,
    SessionInfo,
    build_resource_capabilities,
)

if TYPE_CHECKING:
    from sandbox.lease import SandboxLease
    from sandbox.runtime import PhysicalTerminalRuntime
    from sandbox.terminal import AbstractTerminal


class AgentBayProvider(SandboxProvider):
    """
    AgentBay (Alibaba Cloud) sandbox provider.

    Features:
    - Cloud-based Linux/Windows/Browser environments
    - Context sync for data persistence
    - Pause/resume for cost optimization
    - Rich inspection APIs (metrics, screenshot, processes)
    """

    CATALOG_ENTRY = {"vendor": "Alibaba Cloud", "description": "Remote Linux sandbox", "provider_type": "cloud"}

    name = "agentbay"
    CAPABILITY = ProviderCapability(
        can_pause=True,
        can_resume=True,
        can_destroy=True,
        supports_webhook=False,
        resource_capabilities=build_resource_capabilities(
            filesystem=True,
            terminal=True,
            metrics=True,
            screenshot=True,
            web=True,
            process=True,
            hooks=False,
            mount=False,
        ),
    )
    WORKSPACE_ROOT = "/home/wuying"

    def get_capability(self) -> ProviderCapability:
        return self._capability

    def __init__(
        self,
        api_key: str,
        region_id: str = "ap-southeast-1",
        default_context_path: str = "/home/wuying",
        image_id: str | None = None,
        provider_name: str | None = None,
        supports_pause: bool | None = None,
        supports_resume: bool | None = None,
    ):
        from agentbay import AgentBay

        if provider_name:
            self.name = provider_name
        self.client = AgentBay(api_key=api_key)
        self.default_context_path = default_context_path
        self.image_id = image_id
        self._sessions: dict[str, Any] = {}
        # @@@agentbay-runtime-capability-override - account tier may disable pause/resume; keep provider-type defaults, override per configured instance only.  # noqa: E501
        can_pause = self.CAPABILITY.can_pause if supports_pause is None else supports_pause
        can_resume = self.CAPABILITY.can_resume if supports_resume is None else supports_resume
        self._capability = replace(self.CAPABILITY, can_pause=can_pause, can_resume=can_resume)

    def create_session(self, context_id: str | None = None, thread_id: str | None = None) -> SessionInfo:
        from agentbay import ContextSync, CreateSessionParams

        params = CreateSessionParams()
        if self.image_id:
            params.image_id = self.image_id
        if context_id:
            # @@@ context_id is a human-readable name, not a SdkCtx-* ID.
            # Must call context.get(create=True) to resolve/create the real ID.
            ctx_result = self.client.context.get(context_id, create=True)
            if not ctx_result.success:
                raise RuntimeError(f"Failed to get/create context '{context_id}': {ctx_result.error_message}")
            params.context_syncs = [ContextSync.new(ctx_result.context.id, self.default_context_path)]

        result = self.client.create(params)
        if not result.success:
            raise RuntimeError(f"Failed to create session: {result.error_message}")

        session = self._hydrate_direct_call_session(result.session)
        self._sessions[session.session_id] = session

        return SessionInfo(
            session_id=session.session_id,
            provider=self.name,
            status="running",
        )

    def destroy_session(self, session_id: str, sync: bool = True) -> bool:
        session = self._get_session(session_id)
        result = session.delete(sync_context=sync)
        if result.success:
            self._sessions.pop(session_id, None)
        return result.success

    def pause_session(self, session_id: str) -> bool:
        session = self._get_session(session_id)
        # @@@agentbay-benefit-level - Some AgentBay accounts reject pause/resume with BenefitLevel.NotSupport; keep fail-loud and do not fallback.  # noqa: E501
        result = self.client.pause(session)
        if result.success:
            return True
        message = str(getattr(result, "error_message", "") or getattr(result, "message", "") or "unknown error")
        raise RuntimeError(f"AgentBay pause failed for {session_id}: {message}")

    def resume_session(self, session_id: str) -> bool:
        session = self._get_session(session_id)
        result = self.client.resume(session)
        if not result.success:
            message = str(getattr(result, "error_message", "") or getattr(result, "message", "") or "unknown error")
            raise RuntimeError(f"AgentBay resume failed for {session_id}: {message}")
        get_result = self.client.get(session_id)
        if get_result.success:
            self._sessions[session_id] = get_result.session
        return True

    def get_session_status(self, session_id: str) -> str:
        try:
            result = self.client.get(session_id)
            if result.success:
                status_result = result.session.get_status()
                if status_result.success:
                    return status_result.status.lower()
            else:
                message = str(getattr(result, "error_message", "") or getattr(result, "message", ""))
                if "not found" in message.lower():
                    return "deleted"
        except Exception as exc:
            if "not found" in str(exc).lower():
                return "deleted"
        return "unknown"

    def execute(
        self,
        session_id: str,
        command: str,
        timeout_ms: int = 30000,
        cwd: str | None = None,
    ) -> ProviderExecResult:
        session = self._get_session(session_id)
        timeout_ms = min(timeout_ms, 50000)

        result = session.command.execute_command(
            command=command,
            timeout_ms=timeout_ms,
            cwd=cwd or self.default_context_path,
        )

        if not result.success:
            return ProviderExecResult(output="", error=result.error_message)

        return ProviderExecResult(output=result.output or "")

    def read_file(self, session_id: str, path: str) -> str:
        session = self._get_session(session_id)
        result = session.file_system.read_file(path)
        if not result.success:
            raise OSError(result.error_message)
        return result.content or ""

    def write_file(self, session_id: str, path: str, content: str) -> str:
        session = self._get_session(session_id)
        result = session.file_system.write_file(path, content)
        if not result.success:
            raise OSError(result.error_message)
        return f"Written: {path}"

    def list_dir(self, session_id: str, path: str) -> list[dict]:
        session = self._get_session(session_id)
        result = session.file_system.list_directory(path)
        if not result.success:
            return []
        items = []
        for entry in result.entries or []:
            items.append(
                {
                    "name": entry.name,
                    "type": "directory" if entry.is_directory else "file",
                    "size": entry.size or 0,
                }
            )
        return items

    def get_metrics(self, session_id: str) -> Metrics | None:
        session = self._get_session(session_id)
        result = session.get_metrics()
        if not result.success or not result.metrics:
            return None

        m = result.metrics
        return Metrics(
            cpu_percent=m.cpu_used_pct,
            memory_used_mb=m.mem_used / 1024 / 1024,
            memory_total_mb=m.mem_total / 1024 / 1024,
            disk_used_gb=m.disk_used / 1024 / 1024 / 1024,
            disk_total_gb=m.disk_total / 1024 / 1024 / 1024,
            network_rx_kbps=m.rx_rate_kbyte_per_s,
            network_tx_kbps=m.tx_rate_kbyte_per_s,
        )

    def screenshot(self, session_id: str) -> bytes | str | None:
        session = self._get_session(session_id)
        result = session.computer.screenshot()
        if result.success:
            return getattr(result, "data", None)
        return None

    def list_processes(self, session_id: str) -> list[dict]:
        session = self._get_session(session_id)
        result = session.computer.list_visible_apps()
        if result.success:
            return [{"pid": app.pid, "name": app.name, "cmd": app.cmd} for app in (result.data or [])]
        return []

    def get_web_url(self, session_id: str) -> str | None:
        """Get AgentBay web UI URL for the session."""
        session = self._get_session(session_id)
        return getattr(session, "resource_url", None)

    def _get_session(self, session_id: str):
        """Get session object, fetching from API if not cached."""
        if session_id not in self._sessions:
            result = self.client.get(session_id)
            if not result.success:
                raise RuntimeError(f"Session not found: {session_id}")
            self._sessions[session_id] = result.session
        cached = self._sessions[session_id]
        hydrated = self._hydrate_direct_call_session(cached)
        self._sessions[session_id] = hydrated
        return hydrated

    def _hydrate_direct_call_session(self, session: Any):
        """Ensure cached session carries LinkUrl/token/tool metadata for direct shell calls."""
        if not self._session_needs_direct_call_refresh(session):
            return session
        session_id = str(getattr(session, "session_id", "") or "")
        if not session_id:
            raise RuntimeError("AgentBay session missing session_id")
        refreshed = self.client.get(session_id)
        if not refreshed.success:
            raise RuntimeError(f"Failed to hydrate AgentBay session {session_id}: {refreshed.error_message}")
        return refreshed.session

    @staticmethod
    def _session_needs_direct_call_refresh(session: Any) -> bool:
        # @@@agentbay-direct-call-hydration - shared staging may return a create-session object
        # without token/link_url/mcpTools; refresh once so shell execution stays on the richer LinkUrl path.
        if not getattr(session, "token", ""):
            return True
        if not getattr(session, "link_url", ""):
            return True
        tools = getattr(session, "mcpTools", None)
        return not bool(tools)

    def create_runtime(self, terminal: AbstractTerminal, lease: SandboxLease) -> PhysicalTerminalRuntime:
        from sandbox.runtime import RemoteWrappedRuntime

        return RemoteWrappedRuntime(terminal, lease, self)
