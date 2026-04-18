"""Sandbox detail and cleanup boundary for Monitor."""

from __future__ import annotations

from typing import Any

from backend.web.services import monitor_operation_service
from backend.web.services import monitor_sandbox_projection_service as sandbox_projection
from backend.web.services.thread_visibility import canonical_owner_threads
from storage.runtime import build_sandbox_monitor_repo as make_sandbox_monitor_repo
from storage.runtime import build_thread_repo


def _canonical_live_thread_refs(raw_thread_ids: list[str]) -> list[dict[str, Any]]:
    live_threads = sandbox_projection._live_thread_ids(raw_thread_ids)
    if not live_threads:
        return []

    repo = build_thread_repo()
    try:
        rows = repo.list_by_ids([thread_id for thread_id in raw_thread_ids if thread_id in live_threads])
    finally:
        repo.close()

    canonical = canonical_owner_threads(rows)
    return [{"thread_id": str(row.get("id") or "").strip()} for row in canonical if str(row.get("id") or "").strip()]


def _runtime_row_projection(runtime_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
    cleanup_target: dict[str, Any],
    triage: dict[str, Any],
    provider_name: str,
    runtime_rows: list[dict[str, Any]],
    threads: list[dict[str, Any]],
) -> dict[str, Any]:
    lower_runtime_handle = str(cleanup_target.get("lower_runtime_handle") or "").strip()
    if not lower_runtime_handle:
        return {
            "allowed": False,
            "recommended_action": None,
            "reason": "Sandbox cleanup requires a managed runtime handle.",
            "operation": None,
            "recent_operations": [],
        }
    return monitor_operation_service.build_sandbox_cleanup_truth(
        sandbox_id=sandbox_id,
        triage=triage,
        provider_name=provider_name,
        runtime_rows=runtime_rows,
        threads=threads,
    )


def _build_monitor_sandbox_detail(repo: Any, sandbox_id: str) -> dict[str, Any]:
    sandbox = repo.query_sandbox(sandbox_id)
    if sandbox is None:
        raise KeyError(f"Sandbox not found: {sandbox_id}")
    cleanup_target = repo.query_sandbox_cleanup_target(sandbox_id) or {}

    threads = repo.query_sandbox_threads(sandbox_id)
    runtime_rows = repo.query_sandbox_runtime_rows(sandbox_id)
    runtime_session_id = repo.query_sandbox_instance_id(sandbox_id)
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
            "runtime_session_id": runtime_session_id,
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


def get_monitor_sandbox_detail(sandbox_id: str) -> dict[str, Any]:
    repo = make_sandbox_monitor_repo()
    try:
        return {
            "source": "sandbox_canonical",
            **_build_monitor_sandbox_detail(repo, sandbox_id),
        }
    finally:
        repo.close()


def _sandbox_cleanup_target(sandbox_id: str) -> dict[str, Any]:
    repo = make_sandbox_monitor_repo()
    try:
        sandbox = repo.query_sandbox(sandbox_id)
        cleanup_target = repo.query_sandbox_cleanup_target(sandbox_id) or {}
    finally:
        repo.close()
    if sandbox is None:
        raise KeyError(f"Sandbox not found: {sandbox_id}")

    if not str(cleanup_target.get("lower_runtime_handle") or "").strip():
        raise RuntimeError("monitor sandbox cleanup target missing managed runtime handle")
    return cleanup_target


def request_monitor_sandbox_cleanup(sandbox_id: str) -> dict[str, Any]:
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
        "cleanup": monitor_operation_service.build_sandbox_cleanup_truth(
            sandbox_id=sandbox_id,
            triage=payload.get("triage"),
            provider_name=str(provider.get("id") or sandbox.get("provider_name") or ""),
            runtime_rows=runtime_rows,
            threads=threads,
        ),
    }
    return monitor_operation_service.request_sandbox_cleanup(sandbox_detail)


def get_monitor_operation_detail(operation_id: str) -> dict[str, Any]:
    payload = monitor_operation_service.get_operation_detail(operation_id)
    target = payload.get("target") or {}
    target_type = str(target.get("target_type") or "").strip()
    if target_type == "sandbox":
        sandbox_id = str(target.get("target_id") or "").strip()
        if not sandbox_id:
            raise RuntimeError("monitor operation sandbox target is missing")
        return {**payload, "sandbox_id": sandbox_id}

    return payload
