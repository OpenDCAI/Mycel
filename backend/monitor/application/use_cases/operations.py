"""Monitor cleanup operation truth."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.monitor.infrastructure.persistence import operation_repo
from backend.monitor.mutations import sandbox_mutations as runtime_mutation

_ALLOWED_SANDBOX_CLEANUP_TRIAGE = {"orphan_cleanup", "detached_residue"}
_SANDBOX_CLEANUP_ACTION = "sandbox_cleanup"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _operation_view(operation: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation_id": operation["operation_id"],
        "kind": operation["kind"],
        "target_type": operation["target_type"],
        "target_id": operation["target_id"],
        "status": operation["status"],
        "requested_at": operation["requested_at"],
        "updated_at": operation["updated_at"],
        "summary": operation["summary"],
        "reason": operation["reason"],
        "result_truth": dict(operation.get("result_truth") or {}),
    }


def _append_event(operation: dict[str, Any], *, status: str, message: str) -> None:
    timestamp = _now_iso()
    operation["status"] = status
    operation["updated_at"] = timestamp
    operation["summary"] = message
    operation["events"].append({"at": timestamp, "status": status, "message": message})
    operation_repo.default_monitor_operation_repo().save(operation)


def _new_operation(*, kind: str, target_type: str, target_id: str, reason: str, target: dict[str, Any]) -> dict[str, Any]:
    timestamp = _now_iso()
    operation = {
        "operation_id": f"op-{uuid4().hex[:12]}",
        "kind": kind,
        "target_type": target_type,
        "target_id": target_id,
        "status": "pending",
        "requested_at": timestamp,
        "updated_at": timestamp,
        "summary": "Cleanup queued",
        "reason": reason,
        "target": target,
        "result_truth": {},
        "events": [{"at": timestamp, "status": "pending", "message": "Cleanup queued"}],
    }
    return operation_repo.default_monitor_operation_repo().create(operation)


def _operations_for_target(target_type: str, target_id: str) -> list[dict[str, Any]]:
    return operation_repo.default_monitor_operation_repo().list_for_target(target_type, target_id)


def _has_active_runtime_rows(runtime_rows: list[dict[str, Any]]) -> bool:
    return any(str(item.get("status") or "").strip().lower() == "active" for item in runtime_rows)


def _has_thread_bindings(threads: list[dict[str, Any]]) -> bool:
    return any(str(item.get("thread_id") or "").strip() for item in threads)


def _can_close_stale_active_runtime_rows(*, category: str, runtime_rows: list[dict[str, Any]], threads: list[dict[str, Any]]) -> bool:
    return category == "orphan_cleanup" and _has_active_runtime_rows(runtime_rows) and not _has_thread_bindings(threads)


def build_sandbox_cleanup_truth(
    *,
    sandbox_id: str | None = None,
    triage: dict[str, Any] | None,
    provider_name: str | None,
    runtime_rows: list[dict[str, Any]],
    threads: list[dict[str, Any]],
) -> dict[str, Any]:
    category = str((triage or {}).get("category") or "").strip()
    has_active_runtime_rows = _has_active_runtime_rows(runtime_rows)
    has_thread_bindings = _has_thread_bindings(threads)
    can_close_stale_active_runtime_rows = _can_close_stale_active_runtime_rows(
        category=category,
        runtime_rows=runtime_rows,
        threads=threads,
    )
    provider = str(provider_name or "").strip()

    if has_active_runtime_rows and not can_close_stale_active_runtime_rows:
        allowed = False
        reason = "Sandbox still has active runtime rows and cannot enter managed cleanup."
    elif has_thread_bindings and category != "detached_residue":
        allowed = False
        reason = "Sandbox still has thread bindings and cannot enter managed cleanup."
    elif not provider:
        allowed = False
        reason = "Sandbox has no provider and cannot enter managed cleanup."
    elif category not in _ALLOWED_SANDBOX_CLEANUP_TRIAGE:
        allowed = False
        reason = "Sandbox is not in a managed cleanup state."
    elif category == "orphan_cleanup":
        allowed = True
        if can_close_stale_active_runtime_rows:
            reason = "Sandbox has only stale active runtime rows and can close them before cleanup."
        else:
            reason = "Sandbox is orphan cleanup residue and can enter managed cleanup."
    elif category == "detached_residue":
        allowed = True
        reason = "Sandbox is detached residue and can detach stale thread bindings before cleanup."
    else:
        allowed = False
        reason = "Sandbox is not in a managed cleanup state."

    sandbox_key = str(sandbox_id or "").strip()
    operations = _operations_for_target("sandbox", sandbox_key) if sandbox_key else []
    latest = operations[0] if operations else None

    return {
        "allowed": allowed,
        "recommended_action": _SANDBOX_CLEANUP_ACTION if allowed else None,
        "reason": reason,
        "operation": _operation_view(latest) if latest else None,
        "recent_operations": [_operation_view(operation) for operation in operations[:5]],
    }


def _cleanup_current_truth(*, sandbox_id: str, triage_category: str | None) -> dict[str, Any]:
    return {
        "sandbox_id": sandbox_id,
        "triage_category": triage_category,
    }


def request_sandbox_cleanup(sandbox_detail: dict[str, Any]) -> dict[str, Any]:
    sandbox = sandbox_detail["sandbox"]
    provider = sandbox_detail.get("provider") or {}
    runtime = sandbox_detail.get("runtime") or {}
    threads = sandbox_detail.get("threads") or []
    cleanup = sandbox_detail.get("cleanup") or build_sandbox_cleanup_truth(
        sandbox_id=str(sandbox.get("sandbox_id") or ""),
        triage=sandbox_detail.get("triage"),
        provider_name=str(provider.get("id") or sandbox.get("provider_name") or ""),
        runtime_rows=sandbox_detail.get("runtime_rows") or [],
        threads=threads,
    )

    lower_runtime = sandbox_detail.get("lower_runtime") or {}
    lower_runtime_handle = str(lower_runtime.get("handle") or "")
    sandbox_id = str(sandbox.get("sandbox_id") or "")
    current_truth = _cleanup_current_truth(
        sandbox_id=sandbox_id,
        triage_category=(sandbox_detail.get("triage") or {}).get("category"),
    )
    if not cleanup["allowed"]:
        return {
            "accepted": False,
            "message": cleanup["reason"],
            "operation": None,
            "current_truth": current_truth,
        }
    if not lower_runtime_handle:
        return {
            "accepted": False,
            "message": "Sandbox cleanup requires a managed runtime handle.",
            "operation": None,
            "current_truth": current_truth,
        }

    provider_name = str(provider.get("id") or sandbox.get("provider_name") or "").strip()
    runtime_id = str(runtime.get("runtime_id") or "").strip()
    operation = _new_operation(
        kind=_SANDBOX_CLEANUP_ACTION,
        target_type="sandbox",
        target_id=sandbox_id,
        reason=cleanup["reason"],
        target={
            "target_type": "sandbox",
            "target_id": sandbox_id,
            "provider_id": provider_name,
            "runtime_id": runtime_id or None,
        },
    )
    _append_event(operation, status="running", message="Destroy flow started")

    try:
        category = str((sandbox_detail.get("triage") or {}).get("category") or "").strip()
        runtime_rows = sandbox_detail.get("runtime_rows") or []
        detach_before_cleanup = category == "detached_residue" or _can_close_stale_active_runtime_rows(
            category=category,
            runtime_rows=runtime_rows,
            threads=threads,
        )
        result = runtime_mutation.cleanup_sandbox(
            runtime_mutation.SandboxCleanupRequest(
                lower_runtime_handle=lower_runtime_handle,
                provider_name=provider_name,
                detach_thread_bindings=detach_before_cleanup,
            )
        )
    except Exception as exc:
        operation["result_truth"] = {
            "sandbox_state_before": sandbox.get("observed_state"),
            "sandbox_state_after": sandbox.get("observed_state"),
            "runtime_state_after": str(runtime.get("runtime_id") or "").strip() or None,
        }
        _append_event(operation, status="failed", message=str(exc))
        return {
            "accepted": True,
            "message": str(exc),
            "operation": _operation_view(operation),
            "current_truth": current_truth,
        }

    operation["result_truth"] = {
        "sandbox_state_before": sandbox.get("observed_state"),
        "sandbox_state_after": None,
        "runtime_state_after": None,
        "destroy_result": result.destroy_result,
    }
    _append_event(operation, status="succeeded", message="Sandbox cleanup completed.")
    return {
        "accepted": True,
        "message": "Sandbox cleanup completed.",
        "operation": _operation_view(operation),
        "current_truth": current_truth,
    }


def request_provider_orphan_runtime_cleanup(provider_name: str, runtime_id: str, runtime_truth: dict[str, Any]) -> dict[str, Any]:
    provider = str(provider_name or "").strip()
    runtime = str(runtime_id or "").strip()
    if not provider:
        raise ValueError("provider_name is required")
    if not runtime:
        raise ValueError("runtime_id is required")
    status = str(runtime_truth.get("status") or "").strip().lower()
    source = str(runtime_truth.get("source") or "").strip()
    if source != "provider_orphan" or status != "paused":
        return {
            "accepted": False,
            "message": "Provider orphan runtime cleanup requires a paused provider-orphan runtime.",
            "operation": None,
            "current_truth": {
                "provider_id": provider,
                "runtime_id": runtime,
                "status": status or None,
                "source": source or None,
            },
        }

    target_id = f"{provider}:{runtime}"
    operation = _new_operation(
        kind="provider_orphan_runtime_cleanup",
        target_type="provider_orphan_runtime",
        target_id=target_id,
        reason="Provider orphan runtime is not sandbox-backed and can enter managed cleanup.",
        target={
            "target_type": "provider_orphan_runtime",
            "provider_id": provider,
            "runtime_id": runtime,
        },
    )
    _append_event(operation, status="running", message="Destroy flow started")

    try:
        result = runtime_mutation.cleanup_provider_orphan_runtime(
            runtime_mutation.ProviderOrphanRuntimeCleanupRequest(
                provider_name=provider,
                runtime_id=runtime,
            )
        )
    except Exception as exc:
        operation["result_truth"] = {
            "provider_id": provider,
            "runtime_id": runtime,
        }
        _append_event(operation, status="failed", message=str(exc))
        return {
            "accepted": True,
            "message": str(exc),
            "operation": _operation_view(operation),
            "current_truth": {
                "provider_id": provider,
                "runtime_id": runtime,
            },
        }

    operation["result_truth"] = {"destroy_result": result.destroy_result}
    _append_event(operation, status="succeeded", message="Provider orphan runtime cleanup completed.")
    return {
        "accepted": True,
        "message": "Provider orphan runtime cleanup completed.",
        "operation": _operation_view(operation),
        "current_truth": {
            "provider_id": provider,
            "runtime_id": runtime,
        },
    }


def get_operation_detail(operation_id: str) -> dict[str, Any]:
    payload = operation_repo.default_monitor_operation_repo().get(operation_id)
    if payload is None:
        raise KeyError(f"Operation not found: {operation_id}")

    return {
        "operation": _operation_view(payload),
        "target": payload["target"],
        "result_truth": payload["result_truth"],
        "events": payload["events"],
    }
