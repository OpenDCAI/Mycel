"""Thread state query service for session/terminal/lease status."""

import asyncio
from datetime import timedelta
from typing import Any

from backend.web.utils.helpers import get_lease_timestamps, get_terminal_timestamps


def _resolve_thread_sandbox_instance(mgr: Any, lease: Any) -> Any | None:
    instance = lease.get_instance()
    if instance is not None:
        return instance
    if getattr(mgr.provider_capability, "runtime_kind", None) != "local":
        return None
    # @@@local-status-convergence - local leases can have no bound instance until first capability/session
    # touch. Converge through ensure_active_instance so TaskProgress reflects the actual local runtime
    # instead of showing a fake detached state.
    return lease.ensure_active_instance(mgr.provider)


def _display_sandbox_status(lease: Any, instance: Any) -> str:
    observed = getattr(lease, "observed_state", None)
    return instance.status if observed in {None, "", "detached"} else observed


def get_sandbox_info(agent: Any, thread_id: str, sandbox_type: str) -> dict[str, Any]:
    """Get sandbox session info for a thread.

    Returns:
        Dict with type, status, session_id, terminal_id, error (if any)
    """
    sandbox_info: dict[str, Any] = {"type": sandbox_type, "status": None, "session_id": None}
    if not hasattr(agent, "_sandbox"):
        return sandbox_info

    try:
        mgr = agent._sandbox.manager
        terminal = mgr.get_terminal(thread_id)
        if terminal:
            session = mgr.session_manager.get(thread_id, terminal.terminal_id)
            if session:
                sandbox_info["session_id"] = session.session_id
            lease = mgr.get_lease(terminal.lease_id)
            if lease:
                instance = _resolve_thread_sandbox_instance(mgr, lease)
                if instance:
                    sandbox_info["status"] = _display_sandbox_status(lease, instance)
                    sandbox_info["session_id"] = sandbox_info["session_id"] or instance.instance_id
                else:
                    sandbox_info["status"] = "detached"
            sandbox_info["terminal_id"] = terminal.terminal_id
    except Exception as exc:
        sandbox_info["status"] = "error"
        sandbox_info["error"] = str(exc)

    return sandbox_info


async def get_session_status(agent: Any, thread_id: str) -> dict[str, Any]:
    """Get ChatSession status for a thread.

    Returns:
        Dict with session_id, terminal_id, status, timestamps

    Raises:
        ValueError: If no session found for thread
    """

    def _get_session():
        mgr = agent._sandbox.manager
        terminal = mgr.get_terminal(thread_id)
        if not terminal:
            return None
        return mgr.session_manager.get(thread_id, terminal.terminal_id)

    session = await asyncio.to_thread(_get_session)
    if not session:
        raise ValueError(f"No session found for thread {thread_id}")

    expires_by_idle = session.last_active_at + timedelta(seconds=session.policy.idle_ttl_sec)
    expires_by_duration = session.started_at + timedelta(seconds=session.policy.max_duration_sec)
    expires_at = min(expires_by_idle, expires_by_duration)

    return {
        "thread_id": thread_id,
        "session_id": session.session_id,
        "terminal_id": session.terminal.terminal_id,
        "status": session.status,
        "started_at": session.started_at.isoformat(),
        "last_active_at": session.last_active_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }


async def get_terminal_status(agent: Any, thread_id: str) -> dict[str, Any]:
    """Get AbstractTerminal state for a thread.

    Returns:
        Dict with terminal_id, lease_id, cwd, env_delta, version, timestamps

    Raises:
        ValueError: If no terminal found for thread
    """

    def _get_terminal():
        mgr = agent._sandbox.manager
        return mgr.get_terminal(thread_id)

    terminal = await asyncio.to_thread(_get_terminal)
    if not terminal:
        raise ValueError(f"No terminal found for thread {thread_id}")

    state = terminal.get_state()
    created_at, updated_at = await asyncio.to_thread(get_terminal_timestamps, terminal.terminal_id)
    return {
        "thread_id": thread_id,
        "terminal_id": terminal.terminal_id,
        "lease_id": terminal.lease_id,
        "cwd": state.cwd,
        "env_delta": state.env_delta,
        "version": state.state_version,
        "created_at": created_at,
        "updated_at": updated_at,
    }


async def get_lease_status(agent: Any, thread_id: str) -> dict[str, Any]:
    """Get SandboxLease status for a thread.

    Returns:
        Dict with lease_id, provider_name, states, instance info, timestamps

    Raises:
        ValueError: If no lease found for thread
    """

    def _get_lease():
        mgr = agent._sandbox.manager
        terminal = mgr.get_terminal(thread_id)
        if not terminal:
            return None
        lease = mgr.get_lease(terminal.lease_id)
        if not lease:
            return None
        return lease

    lease = await asyncio.to_thread(_get_lease)
    if not lease:
        raise ValueError(f"No lease found for thread {thread_id}")

    instance = lease.get_instance()
    created_at, updated_at = await asyncio.to_thread(get_lease_timestamps, lease.lease_id)
    return {
        "thread_id": thread_id,
        "lease_id": lease.lease_id,
        "provider_name": lease.provider_name,
        "desired_state": lease.desired_state,
        "observed_state": lease.observed_state,
        "version": lease.version,
        "last_error": lease.last_error,
        "instance": {
            "instance_id": instance.instance_id if instance else None,
            "state": instance.status if instance else None,
            "started_at": instance.created_at.isoformat() if instance and instance.created_at else None,
        }
        if instance
        else None,
        "created_at": created_at,
        "updated_at": updated_at,
    }
