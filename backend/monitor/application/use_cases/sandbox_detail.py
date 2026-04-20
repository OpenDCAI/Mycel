"""Sandbox detail and cleanup boundary for Monitor."""

from __future__ import annotations

from backend.monitor.application.use_cases import operations, sandbox_projection
from backend.monitor.infrastructure.read_models import sandbox_read_service, thread_read_service


def _canonical_live_thread_refs(raw_thread_ids: list[str]) -> list[dict[str, str]]:
    live_threads = sandbox_projection._live_thread_ids(raw_thread_ids)
    return thread_read_service.load_canonical_live_thread_refs(raw_thread_ids, live_threads)


def _runtime_row_projection(runtime_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "chat_session_id": item.get("chat_session_id"),
            "thread_id": item.get("thread_id"),
            "status": item.get("status"),
            "started_at": item.get("started_at"),
            "ended_at": item.get("ended_at"),
            "close_reason": item.get("close_reason"),
        }
        for item in runtime_rows
    ]


def _sandbox_detail_cleanup_truth(
    *,
    sandbox_id: str,
    cleanup_target: dict[str, object],
    triage: dict[str, object],
    provider_name: str,
    runtime_rows: list[dict[str, object]],
    threads: list[dict[str, str]],
) -> dict[str, object]:
    lower_runtime_handle = str(cleanup_target.get("lower_runtime_handle") or "").strip()
    if not lower_runtime_handle:
        return {
            "allowed": False,
            "recommended_action": None,
            "reason": "Sandbox cleanup requires a managed runtime handle.",
            "operation": None,
            "recent_operations": [],
        }
    try:
        return operations.build_sandbox_cleanup_truth(
            sandbox_id=sandbox_id,
            triage=triage,
            provider_name=provider_name,
            runtime_rows=runtime_rows,
            threads=threads,
        )
    except RuntimeError as err:
        if "observability.monitor_operations is missing" not in str(err):
            raise
        return {
            "allowed": False,
            "recommended_action": None,
            "reason": "Monitor cleanup history is unavailable in the current process.",
            "operation": None,
            "recent_operations": [],
        }


def _build_monitor_sandbox_detail(rows: dict[str, object]) -> dict[str, object]:
    sandbox = rows["sandbox"]
    cleanup_target = rows["cleanup_target"]
    threads = rows["threads"]
    runtime_rows = rows["runtime_rows"]
    runtime_id = rows["runtime_id"]
    runtime_projection = _runtime_row_projection(runtime_rows)

    raw_thread_ids = [str(item.get("thread_id") or "").strip() for item in threads if str(item.get("thread_id") or "").strip()]
    live_thread_refs = _canonical_live_thread_refs(raw_thread_ids)
    badge = sandbox_projection._make_badge(sandbox.get("desired_state"), sandbox.get("observed_state"))
    triage = sandbox_projection._classify_sandbox_triage(
        thread_id=live_thread_refs[0]["thread_id"] if live_thread_refs else None,
        badge=badge,
        observed_state=sandbox.get("observed_state"),
        desired_state=sandbox.get("desired_state"),
        updated_at=sandbox.get("updated_at"),
    )
    provider_name = str(sandbox.get("provider_name") or "").strip()
    return {
        "sandbox": {
            "sandbox_id": sandbox.get("sandbox_id"),
            "provider_name": provider_name,
            "desired_state": sandbox.get("desired_state"),
            "observed_state": sandbox.get("observed_state"),
            "current_instance_id": sandbox.get("current_instance_id"),
            "updated_at": sandbox.get("updated_at"),
            "last_error": sandbox.get("last_error"),
            "badge": badge,
        },
        "triage": triage,
        "provider": {
            "id": provider_name,
            "name": provider_name,
        },
        "runtime": {
            "runtime_id": runtime_id,
        },
        "threads": live_thread_refs,
        "runtime_rows": runtime_projection,
        "cleanup": _sandbox_detail_cleanup_truth(
            sandbox_id=str(sandbox.get("sandbox_id") or "").strip(),
            cleanup_target=cleanup_target,
            triage=triage,
            provider_name=provider_name,
            runtime_rows=runtime_projection,
            threads=live_thread_refs,
        ),
    }


def get_monitor_sandbox_detail(sandbox_id: str) -> dict[str, object]:
    rows = sandbox_read_service.load_sandbox_detail_rows(sandbox_id)
    return {
        "source": "sandbox_canonical",
        **_build_monitor_sandbox_detail(rows),
    }


def _sandbox_cleanup_target(sandbox_id: str) -> dict[str, object]:
    cleanup_target = sandbox_read_service.load_sandbox_cleanup_target(sandbox_id)
    if not str(cleanup_target.get("lower_runtime_handle") or "").strip():
        raise RuntimeError("monitor sandbox cleanup target missing managed runtime handle")
    return cleanup_target


def request_monitor_sandbox_cleanup(
    sandbox_id: str,
    *,
    runtime_mutation_executor,
) -> dict[str, object]:
    payload = get_monitor_sandbox_detail(sandbox_id)
    sandbox = payload["sandbox"]
    provider = payload.get("provider") or {}
    runtime = payload.get("runtime") or {}
    threads = payload.get("threads") or []
    runtime_rows = payload.get("runtime_rows") or []

    cleanup_target = _sandbox_cleanup_target(sandbox_id)
    lower_runtime_handle = str(cleanup_target.get("lower_runtime_handle") or "").strip()
    sandbox_detail = {
        "sandbox": sandbox,
        "lower_runtime": {"handle": lower_runtime_handle},
        "triage": payload.get("triage"),
        "provider": provider,
        "runtime": runtime,
        "threads": threads,
        "runtime_rows": runtime_rows,
        "cleanup": operations.build_sandbox_cleanup_truth(
            sandbox_id=sandbox_id,
            triage=payload.get("triage"),
            provider_name=str(provider.get("id") or sandbox.get("provider_name") or ""),
            runtime_rows=runtime_rows,
            threads=threads,
        ),
    }
    return operations.request_sandbox_cleanup(
        sandbox_detail,
        runtime_mutation_executor=runtime_mutation_executor,
    )


def get_monitor_operation_detail(operation_id: str) -> dict[str, object]:
    payload = operations.get_operation_detail(operation_id)
    target = payload.get("target") or {}
    target_type = str(target.get("target_type") or "").strip()
    if target_type == "sandbox":
        sandbox_id = str(target.get("target_id") or "").strip()
        if not sandbox_id:
            raise RuntimeError("monitor operation sandbox target is missing")
        return {**payload, "sandbox_id": sandbox_id}

    return payload
