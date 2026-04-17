"""Thread state query service for sandbox and lease status."""

import asyncio
from typing import Any

from backend.web.services.thread_runtime_binding_service import resolve_thread_runtime_binding


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
    if observed in {None, "", "detached"}:
        status = getattr(instance, "status", None)
        if not isinstance(status, str) or not status:
            raise RuntimeError("Sandbox instance missing status")
        return status
    if not isinstance(observed, str):
        raise RuntimeError("Lease observed_state must be a string when present")
    return observed


def get_sandbox_info(agent: Any, thread_id: str, sandbox_type: str) -> dict[str, Any]:
    """Get sandbox session info for a thread.

    Returns:
        Dict with type, status, error (if any)
    """
    sandbox_info: dict[str, Any] = {"type": sandbox_type, "status": None}
    if not hasattr(agent, "_sandbox"):
        return sandbox_info

    try:
        mgr = agent._sandbox.manager
        terminal = mgr.get_terminal(thread_id)
        if terminal:
            lease = mgr.get_lease(terminal.lease_id)
            if lease:
                instance = _resolve_thread_sandbox_instance(mgr, lease)
                if instance:
                    sandbox_info["status"] = _display_sandbox_status(lease, instance)
                else:
                    sandbox_info["status"] = "detached"
    except Exception as exc:
        sandbox_info["status"] = "error"
        sandbox_info["error"] = str(exc)

    return sandbox_info


def _required_text(row: dict[str, Any], key: str, label: str) -> str:
    value = str(row.get(key) or "").strip()
    if not value:
        raise RuntimeError(f"{label}.{key} is required")
    return value


async def get_lease_status_from_repos(
    thread_repo: Any,
    workspace_repo: Any,
    sandbox_repo: Any,
    lease_repo: Any,
    thread_id: str,
) -> dict[str, Any] | None:
    """Get SandboxLease status from storage repos without bootstrapping an agent."""
    binding = await asyncio.to_thread(
        resolve_thread_runtime_binding,
        thread_repo=thread_repo,
        workspace_repo=workspace_repo,
        sandbox_repo=sandbox_repo,
        thread_id=thread_id,
    )
    lease_id = str(binding.sandbox_config.get("legacy_lease_id") or "").strip()
    if not lease_id:
        return None
    lease = await asyncio.to_thread(lease_repo.get, lease_id)
    if not lease:
        return None

    instance = lease.get("_instance")
    return {
        "thread_id": thread_id,
        "lease_id": _required_text(lease, "lease_id", "lease"),
        "provider_name": _required_text(lease, "provider_name", "lease"),
        "desired_state": lease.get("desired_state"),
        "observed_state": lease.get("observed_state"),
        "version": lease.get("version"),
        "last_error": lease.get("last_error"),
        "instance": {
            "instance_id": instance.get("instance_id"),
            "state": instance.get("status"),
            "started_at": instance.get("created_at"),
        }
        if instance
        else None,
        "created_at": _required_text(lease, "created_at", "lease"),
        "updated_at": _required_text(lease, "updated_at", "lease"),
    }
