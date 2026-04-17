"""Thread state query service for sandbox status."""

import asyncio
from typing import Any

from backend.web.services.thread_runtime_binding_service import resolve_thread_runtime_binding


def _display_repo_sandbox_status(lease: dict[str, Any], instance: dict[str, Any]) -> str:
    observed = lease.get("observed_state")
    if observed in {None, "", "detached"}:
        status = instance.get("status")
        if not isinstance(status, str) or not status:
            raise RuntimeError("Sandbox instance missing status")
        return status
    if not isinstance(observed, str):
        raise RuntimeError("Lease observed_state must be a string when present")
    return observed


def get_sandbox_info(app: Any, thread_id: str, sandbox_type: str) -> dict[str, Any]:
    """Get sandbox info for a thread from the target runtime binding."""
    sandbox_info: dict[str, Any] = {"type": sandbox_type, "status": None}

    try:
        binding = resolve_thread_runtime_binding(
            thread_repo=app.state.thread_repo,
            workspace_repo=app.state.workspace_repo,
            sandbox_repo=app.state.sandbox_repo,
            thread_id=thread_id,
        )
        lease_id = str(binding.sandbox_config.get("legacy_lease_id") or "").strip()
        if not lease_id:
            return sandbox_info
        lease = app.state.lease_repo.get(lease_id)
        if not lease:
            return sandbox_info
        instance = lease.get("_instance")
        if instance:
            sandbox_info["status"] = _display_repo_sandbox_status(lease, instance)
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


async def get_sandbox_status_from_repos(
    thread_repo: Any,
    workspace_repo: Any,
    sandbox_repo: Any,
    lease_repo: Any,
    thread_id: str,
) -> dict[str, Any] | None:
    """Get thread sandbox status from storage repos without bootstrapping an agent."""
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
