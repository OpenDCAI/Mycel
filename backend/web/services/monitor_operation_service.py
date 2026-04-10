"""Monitor cleanup operation truth."""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Any
from uuid import uuid4

_LOCK = Lock()
_OPERATIONS: dict[str, dict[str, Any]] = {}
_TARGET_INDEX: dict[tuple[str, str], list[str]] = {}
_ALLOWED_LEASE_CLEANUP_TRIAGE = {"detached_residue", "orphan_cleanup"}


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
    }


def _append_event(operation: dict[str, Any], *, status: str, message: str) -> None:
    timestamp = _now_iso()
    operation["status"] = status
    operation["updated_at"] = timestamp
    operation["summary"] = message
    operation["events"].append({"at": timestamp, "status": status, "message": message})


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
    with _LOCK:
        _OPERATIONS[operation["operation_id"]] = operation
        _TARGET_INDEX.setdefault((target_type, target_id), []).insert(0, operation["operation_id"])
    return operation


def _operations_for_target(target_type: str, target_id: str) -> list[dict[str, Any]]:
    with _LOCK:
        ids = list(_TARGET_INDEX.get((target_type, target_id), []))
        return [dict(_OPERATIONS[operation_id]) for operation_id in ids if operation_id in _OPERATIONS]


def _has_active_sessions(sessions: list[dict[str, Any]]) -> bool:
    return any(str(item.get("status") or "").strip().lower() == "active" for item in sessions)


def build_lease_cleanup_truth(
    *,
    lease_id: str,
    triage: dict[str, Any] | None,
    provider_name: str | None,
    runtime_session_id: str | None,
    sessions: list[dict[str, Any]],
) -> dict[str, Any]:
    category = str((triage or {}).get("category") or "").strip()
    has_active_sessions = _has_active_sessions(sessions)
    provider = str(provider_name or "").strip()
    runtime = str(runtime_session_id or "").strip()

    if has_active_sessions:
        allowed = False
        reason = "Lease still has active thread bindings and cannot enter managed cleanup."
    elif not provider:
        allowed = False
        reason = "Lease has no provider and cannot enter managed cleanup."
    elif not runtime:
        allowed = False
        reason = "Lease has no runtime session to destroy."
    elif category not in _ALLOWED_LEASE_CLEANUP_TRIAGE:
        allowed = False
        reason = "Lease is not in a managed cleanup state."
    elif category == "orphan_cleanup":
        allowed = True
        reason = "Lease is orphan cleanup residue and can enter managed cleanup."
    else:
        allowed = True
        reason = "Lease is detached residue and can enter managed cleanup."

    operations = _operations_for_target("lease", lease_id)
    latest = operations[0] if operations else None

    return {
        "allowed": allowed,
        "recommended_action": "lease_cleanup" if allowed else None,
        "reason": reason,
        "operation": _operation_view(latest) if latest else None,
        "recent_operations": [_operation_view(operation) for operation in operations[:5]],
    }


def request_lease_cleanup(lease_detail: dict[str, Any]) -> dict[str, Any]:
    lease = lease_detail["lease"]
    provider = lease_detail.get("provider") or {}
    runtime = lease_detail.get("runtime") or {}
    threads = lease_detail.get("threads") or []
    cleanup = lease_detail.get("cleanup") or build_lease_cleanup_truth(
        lease_id=str(lease.get("lease_id") or ""),
        triage=lease_detail.get("triage"),
        provider_name=str(provider.get("id") or lease.get("provider_name") or ""),
        runtime_session_id=str(runtime.get("runtime_session_id") or ""),
        sessions=lease_detail.get("sessions") or [],
    )

    lease_id = str(lease.get("lease_id") or "")
    if not cleanup["allowed"]:
        return {
            "accepted": False,
            "message": cleanup["reason"],
            "operation": None,
            "current_truth": {
                "lease_id": lease_id,
                "triage_category": (lease_detail.get("triage") or {}).get("category"),
            },
        }

    provider_name = str(provider.get("id") or lease.get("provider_name") or "").strip()
    runtime_session_id = str(runtime.get("runtime_session_id") or "").strip()
    thread_ids = [str(item.get("thread_id") or "").strip() for item in threads if str(item.get("thread_id") or "").strip()]

    operation = _new_operation(
        kind="lease_cleanup",
        target_type="lease",
        target_id=lease_id,
        reason=cleanup["reason"],
        target={
            "target_type": "lease",
            "target_id": lease_id,
            "provider_id": provider_name,
            "runtime_session_id": runtime_session_id or None,
            "thread_ids": thread_ids,
        },
    )
    _append_event(operation, status="running", message="Destroy flow started")

    from backend.web.services.sandbox_service import mutate_sandbox_session

    try:
        result = mutate_sandbox_session(session_id=runtime_session_id, action="destroy", provider_hint=provider_name)
    except Exception as exc:
        operation["result_truth"] = {
            "lease_state_before": lease.get("observed_state"),
            "lease_state_after": lease.get("observed_state"),
            "runtime_state_after": runtime_session_id or None,
            "thread_state_after": thread_ids or None,
        }
        _append_event(operation, status="failed", message=str(exc))
        return {
            "accepted": True,
            "message": str(exc),
            "operation": _operation_view(operation),
            "current_truth": {
                "lease_id": lease_id,
                "triage_category": (lease_detail.get("triage") or {}).get("category"),
            },
        }

    operation["result_truth"] = {
        "lease_state_before": lease.get("observed_state"),
        "lease_state_after": None,
        "runtime_state_after": None,
        "thread_state_after": thread_ids or None,
        "destroy_result": result,
    }
    _append_event(operation, status="succeeded", message="Lease cleanup completed.")
    return {
        "accepted": True,
        "message": "Lease cleanup completed.",
        "operation": _operation_view(operation),
        "current_truth": {
            "lease_id": lease_id,
            "triage_category": (lease_detail.get("triage") or {}).get("category"),
        },
    }


def get_operation_detail(operation_id: str) -> dict[str, Any]:
    with _LOCK:
        operation = _OPERATIONS.get(operation_id)
        if operation is None:
            raise KeyError(f"Operation not found: {operation_id}")
        payload = dict(operation)

    return {
        "operation": _operation_view(payload),
        "target": payload["target"],
        "result_truth": payload["result_truth"],
        "events": payload["events"],
    }
