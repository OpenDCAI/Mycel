"""Monitor service: lease observation + health diagnostics."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Any

from backend.web.services.sandbox_service import init_providers_and_managers, load_all_sessions
from eval.storage import TrajectoryStore
from storage.runtime import (
    build_chat_session_repo as make_chat_session_repo,
)
from storage.runtime import (
    build_lease_repo as make_lease_repo,
)
from storage.runtime import (
    build_runtime_health_monitor_repo as make_runtime_health_monitor_repo,
)
from storage.runtime import (
    build_sandbox_monitor_repo as make_sandbox_monitor_repo,
)
from storage.runtime import (
    current_storage_strategy,
    resolve_runtime_health_monitor_db_path,
)


# ---------------------------------------------------------------------------
# Mapping helpers (private)
# ---------------------------------------------------------------------------
def make_eval_store() -> TrajectoryStore:
    return TrajectoryStore()


def _format_time_ago(iso_timestamp: str | None) -> str:
    if not iso_timestamp:
        return "never"
    # @@@naive-local-time - SQLite timestamps in this module are local-time strings.
    if "Z" in iso_timestamp:
        iso_timestamp = iso_timestamp.replace("Z", "")
    if "+" in iso_timestamp:
        iso_timestamp = iso_timestamp.split("+")[0]
    dt = datetime.fromisoformat(iso_timestamp)
    delta = datetime.now() - dt
    if delta.days > 0:
        return f"{delta.days}d ago"
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours}h ago"
    minutes = (delta.seconds % 3600) // 60
    if minutes > 0:
        return f"{minutes}m ago"
    return "just now"


def _make_badge(desired: str | None, observed: str | None) -> dict[str, Any]:
    if not desired and not observed:
        return {"desired": None, "observed": None, "converged": True, "color": "green", "text": "destroyed"}
    if desired == observed:
        return {"desired": desired, "observed": observed, "converged": True, "color": "green", "text": observed}
    return {
        "desired": desired,
        "observed": observed,
        "converged": False,
        "color": "yellow",
        "text": f"{observed} -> {desired}",
    }


def _thread_ref(thread_id: str | None) -> dict[str, Any]:
    return {
        "thread_id": thread_id,
        "is_orphan": not thread_id,
    }


def _lease_ref(
    lease_id: str | None,
    provider: str | None,
    instance_id: str | None = None,
) -> dict[str, Any]:
    return {
        "lease_id": lease_id,
        "provider": provider,
        "instance_id": instance_id,
    }


LEASE_SEMANTIC_ORDER = [
    "orphan_diverged",
    "diverged",
    "orphan",
    "healthy",
]

LEASE_SEMANTIC_META = {
    "orphan_diverged": {
        "title": "Orphaned + Diverged",
        "description": "Lease lost thread binding while desired and observed state still disagree.",
    },
    "diverged": {
        "title": "Diverged",
        "description": "Lease is still attached to a thread, but runtime state has not converged.",
    },
    "orphan": {
        "title": "Orphans",
        "description": "Lease has no active thread binding. Usually cleanup or historical residue.",
    },
    "healthy": {
        "title": "Healthy",
        "description": "Lease has a thread binding and desired state matches observed state.",
    },
}


EVAL_NOTE_KEYS = [
    "runner",
    "rc",
    "sandbox",
    "run_dir",
    "stdout_log",
    "stderr_log",
]

LEASE_TRIAGE_ORDER = [
    "active_drift",
    "detached_residue",
    "orphan_cleanup",
    "healthy_capacity",
]

LEASE_TRIAGE_META = {
    "active_drift": {
        "title": "Active Drift",
        "description": "Leases whose desired and observed state still disagree recently enough to warrant active operator attention.",
        "tone": "warning",
    },
    "detached_residue": {
        "title": "Detached Residue",
        "description": (
            "Leases still marked desired=running but observed=detached long after the runtime "
            "stopped moving. Usually cleanup debt, not live pressure."
        ),
        "tone": "danger",
    },
    "orphan_cleanup": {
        "title": "Orphan Cleanup",
        "description": "Lease rows that have already lost thread binding and mainly represent cleanup backlog or historical residue.",
        "tone": "warning",
    },
    "healthy_capacity": {
        "title": "Healthy Capacity",
        "description": "Leases with attached thread context and converged runtime state.",
        "tone": "success",
    },
}

DETACHED_RESIDUE_THRESHOLD_HOURS = 4.0
RESOURCE_CLEANUP_ALLOWED_CATEGORIES = {"detached_residue", "orphan_cleanup"}
ACTIVE_CHAT_SESSION_STATUSES = {"active", "idle", "paused"}


def _classify_lease_semantics(*, thread_id: str | None, badge: dict[str, Any]) -> dict[str, str]:
    is_orphan = not bool(thread_id)
    is_converged = bool(badge.get("converged"))
    if is_orphan and not is_converged:
        category = "orphan_diverged"
    elif not is_converged:
        category = "diverged"
    elif is_orphan:
        category = "orphan"
    else:
        category = "healthy"
    meta = LEASE_SEMANTIC_META[category]
    return {
        "category": category,
        "title": meta["title"],
        "description": meta["description"],
    }


def _parse_local_timestamp(iso_timestamp: str | None) -> datetime | None:
    if not iso_timestamp:
        return None
    cleaned = iso_timestamp
    if "Z" in cleaned:
        cleaned = cleaned.replace("Z", "")
    if "+" in cleaned:
        cleaned = cleaned.split("+")[0]
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _hours_since(iso_timestamp: str | None) -> float | None:
    dt = _parse_local_timestamp(iso_timestamp)
    if dt is None:
        return None
    delta = datetime.now() - dt
    return delta.total_seconds() / 3600


def _classify_lease_triage(
    *,
    thread_id: str | None,
    badge: dict[str, Any],
    observed_state: str | None,
    desired_state: str | None,
    updated_at: str | None,
) -> dict[str, Any]:
    observed = str(observed_state or "").strip().lower() or None
    desired = str(desired_state or "").strip().lower() or None
    age_hours = _hours_since(updated_at)
    is_orphan = not bool(thread_id)
    is_converged = bool(badge.get("converged"))

    if is_orphan:
        key = "orphan_cleanup"
    elif is_converged:
        key = "healthy_capacity"
    elif observed == "detached" and desired == "running" and age_hours is not None and age_hours >= DETACHED_RESIDUE_THRESHOLD_HOURS:
        key = "detached_residue"
    else:
        key = "active_drift"

    meta = LEASE_TRIAGE_META[key]
    return {
        "category": key,
        "title": meta["title"],
        "description": meta["description"],
        "tone": meta["tone"],
        "age_hours": age_hours,
    }


def _cleanable_lease_ids(lease_ids: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in lease_ids:
        lease_id = str(raw or "").strip()
        if not lease_id or lease_id in seen:
            continue
        seen.add(lease_id)
        cleaned.append(lease_id)
    if not cleaned:
        raise ValueError("lease_ids must contain at least one non-empty lease id")
    return cleaned


def _triage_category_for_row(row: dict[str, Any]) -> str:
    badge = _make_badge(row.get("desired_state"), row.get("observed_state"))
    triage = _classify_lease_triage(
        thread_id=row.get("thread_id"),
        badge=badge,
        observed_state=row.get("observed_state"),
        desired_state=row.get("desired_state"),
        updated_at=row.get("updated_at"),
    )
    return str(triage["category"])


def _extract_eval_note_value(notes: str, key: str) -> str | None:
    match = re.search(rf"(?:^|[ |]){re.escape(key)}=([^ ]+)", notes)
    if not match:
        return None
    return match.group(1).strip()


def build_evaluation_operator_surface(
    *,
    status: str,
    notes: str,
    score: dict[str, Any],
    threads_total: int,
    threads_running: int,
    threads_done: int,
) -> dict[str, Any]:
    extracted = {key: _extract_eval_note_value(notes, key) for key in EVAL_NOTE_KEYS}
    rc_text = extracted.get("rc")
    try:
        rc = int(rc_text) if rc_text is not None else None
    except ValueError:
        rc = None

    scored = bool(score.get("scored"))
    score_gate = str(score.get("score_gate") or "provisional")
    artifacts = [
        {
            "label": "Run directory",
            "path": score.get("run_dir") or extracted.get("run_dir"),
        },
        {"label": "Run manifest", "path": score.get("manifest_path")},
        {"label": "STDOUT log", "path": extracted.get("stdout_log")},
        {"label": "STDERR log", "path": extracted.get("stderr_log")},
        {"label": "Eval summary", "path": score.get("eval_summary_path")},
        {"label": "Trace summaries", "path": score.get("trace_summaries_path")},
    ]
    artifacts = [
        {
            **item,
            "status": "present" if item["path"] else "missing",
        }
        for item in artifacts
    ]
    artifact_summary = {
        "present": sum(1 for item in artifacts if item["status"] == "present"),
        "missing": sum(1 for item in artifacts if item["status"] == "missing"),
        "total": len(artifacts),
    }

    facts = [
        {"label": "Status", "value": status},
        {"label": "Score gate", "value": score_gate},
        {"label": "Threads materialized", "value": str(threads_total)},
        {"label": "Threads running", "value": str(threads_running)},
        {"label": "Threads done", "value": str(threads_done)},
    ]
    runner = extracted.get("runner")
    if runner:
        facts.append({"label": "Runner", "value": runner})
    if rc is not None:
        facts.append({"label": "Exit code", "value": str(rc)})

    kind = "collecting_runtime_evidence"
    tone = "default"
    headline = "Evaluation is still collecting runtime evidence."
    summary = "Use the artifacts below to inspect progress and confirm whether thread rows are materializing."
    next_steps = [
        "Open the run manifest to confirm the slice payload and output directory.",
        "Inspect stdout/stderr before assuming the run is healthy.",
    ]

    if status == "provisional" and not scored:
        kind = "provisional_waiting_for_summary"
        tone = "warning"
        headline = "Evaluation is provisional. Final score is blocked."
        summary = "This run has not produced the final eval summary yet, so publishable scoring is intentionally withheld."
        next_steps = [
            "Check whether eval_summary_path is still missing because the run is ongoing or because the runner exited early.",
            "Use stdout/stderr logs to confirm whether the solve phase actually started.",
        ]

    if rc is not None and rc != 0 and threads_total == 0:
        kind = "bootstrap_failure"
        tone = "danger"
        headline = "Runner exited before evaluation threads materialized."
        summary = "Treat this as a bootstrap failure, not as an empty successful run. No evaluation thread rows were created."
        next_steps = [
            "Inspect STDERR first to find the failing bootstrap step.",
            "Use the run manifest and stdout log to confirm whether the slice was prepared before exit.",
            "Re-run only after the failing dependency or model configuration is understood.",
        ]
    elif status == "running" and threads_total == 0 and threads_running > 0:
        kind = "running_waiting_for_threads"
        tone = "default"
        headline = "Evaluation is actively running while thread rows catch up."
        summary = (
            "The runner is alive, but thread rows have not materialized yet. Treat this as an ingestion lag window, not as an empty run."
        )
        next_steps = [
            "Refresh after the first thread row materializes.",
            "Use stdout/stderr to confirm the solve loop is still advancing.",
        ]
    elif status == "running":
        kind = "running_active"
        tone = "default"
        headline = "Evaluation is actively running."
        summary = "Thread rows and traces may lag behind the runner. Use live progress and logs before declaring drift."
        next_steps = [
            "Refresh after new thread rows materialize.",
            "Inspect traces only after the first active thread appears.",
        ]
    elif status == "completed_with_errors" and scored:
        kind = "completed_with_errors"
        tone = "warning"
        headline = "Evaluation completed with recorded errors."
        summary = (
            "Some thread rows reached completion, but at least one instance recorded an error. Treat this as reviewable but not clean."
        )
        next_steps = [
            "Inspect error-bearing threads before comparing this run against cleaner baselines.",
            "Use eval summary and trace summaries to isolate failing instances.",
        ]
    elif status == "completed" and scored:
        kind = "completed_publishable"
        tone = "success"
        headline = "Evaluation finished with a publishable score surface."
        summary = "Score artifacts are present. Use the thread table to drill into trace-level evidence."
        next_steps = [
            "Open threads with low-quality traces and inspect tool-call detail.",
            "Use the eval summary and trace summaries to compare runs.",
        ]

    return {
        "status": status,
        "kind": kind,
        "tone": tone,
        "headline": headline,
        "summary": summary,
        "facts": facts,
        "artifacts": artifacts,
        "artifact_summary": artifact_summary,
        "next_steps": next_steps,
        "raw_notes": notes,
    }


def _evaluation_unavailable_surface() -> dict[str, Any]:
    return {
        "status": "unavailable",
        "kind": "unavailable",
        "tone": "warning",
        "headline": "Evaluation operator truth is not wired in this runtime yet.",
        "summary": "Monitor can report that evaluation truth is unavailable without pretending nothing is happening.",
        "facts": [{"label": "Status", "value": "unavailable"}],
        "artifacts": [],
        "artifact_summary": {"present": 0, "missing": 0, "total": 0},
        "next_steps": ["Restore a truthful evaluation runtime source before reviving the monitor evaluation page."],
        "raw_notes": None,
    }


def _evaluation_no_runs_surface() -> dict[str, Any]:
    return {
        "status": "idle",
        "kind": "no_recorded_runs",
        "tone": "default",
        "headline": "No persisted evaluation runs are available yet.",
        "summary": "Evaluation storage is wired, but there are no recorded runs to report yet.",
        "facts": [{"label": "Status", "value": "idle"}],
        "artifacts": [],
        "artifact_summary": {"present": 0, "missing": 0, "total": 0},
        "next_steps": ["Run an evaluation to populate the operator surface with persisted runtime truth."],
        "raw_notes": None,
    }


def _normalize_persisted_eval_status(raw_status: str | None) -> tuple[str, str, str, str]:
    status = str(raw_status or "").strip().lower()
    # @@@eval-status-normalization - persisted eval_runs only record coarse terminal status,
    # so monitor must normalize them without pretending the old manifest/thread truth still exists.
    if status == "running":
        return (
            "running",
            "running_recorded",
            "default",
            "Latest persisted evaluation run is still marked running.",
        )
    if status in {"error", "failed", "cancelled"}:
        return (
            "completed_with_errors",
            "run_recorded_with_errors",
            "warning",
            "Latest persisted evaluation run finished with errors.",
        )
    if status == "completed":
        return (
            "completed",
            "completed_recorded",
            "success",
            "Latest persisted evaluation run completed successfully.",
        )
    return (
        "provisional",
        "persisted_status_unknown",
        "warning",
        "Latest persisted evaluation run reported an unknown status.",
    )


def _build_persisted_evaluation_surface(run: dict[str, Any], metrics_rows: list[dict[str, Any]]) -> dict[str, Any]:
    status, kind, tone, headline = _normalize_persisted_eval_status(run.get("status"))
    metrics_by_tier = {str(row.get("tier") or "").strip().lower(): row.get("metrics") or {} for row in metrics_rows}
    system_metrics = metrics_by_tier.get("system") or {}
    objective_metrics = metrics_by_tier.get("objective") or {}
    facts = [
        {"label": "Status", "value": status},
        {"label": "Run ID", "value": str(run.get("id") or "-")},
        {"label": "Thread ID", "value": str(run.get("thread_id") or "-")},
        {"label": "Started At", "value": str(run.get("started_at") or "-")},
        {"label": "Finished At", "value": str(run.get("finished_at") or "-")},
        {"label": "Metric Tiers", "value": str(len(metrics_rows))},
    ]
    user_message = str(run.get("user_message") or "").strip()
    if user_message:
        facts.append({"label": "User Message", "value": user_message})
    total_tokens = system_metrics.get("total_tokens")
    if total_tokens is not None:
        facts.append({"label": "Total tokens", "value": str(total_tokens)})
    llm_call_count = system_metrics.get("llm_call_count")
    if llm_call_count is not None:
        facts.append({"label": "LLM calls", "value": str(llm_call_count)})
    tool_call_count = system_metrics.get("tool_call_count")
    if tool_call_count is not None:
        facts.append({"label": "Tool calls", "value": str(tool_call_count)})
    total_duration_ms = objective_metrics.get("total_duration_ms")
    if total_duration_ms is not None:
        duration_value = int(total_duration_ms) if float(total_duration_ms).is_integer() else total_duration_ms
        facts.append({"label": "Duration (ms)", "value": str(duration_value)})

    return {
        "status": status,
        "kind": kind,
        "tone": tone,
        "headline": headline,
        "summary": (
            "Monitor is reading the latest persisted eval run from eval_runs/eval_metrics. "
            "Legacy manifest, artifact, and thread-materialization detail are not wired in this slice."
        ),
        "facts": facts,
        "artifacts": [],
        "artifact_summary": {"present": 0, "missing": 0, "total": 0},
        "next_steps": [
            "Use the persisted run and metric facts here as the current source of truth.",
            "Restore richer artifact and thread drilldown in later evaluation runtime slices if still needed.",
        ],
        "raw_notes": None,
    }


def get_monitor_evaluation_truth() -> dict[str, Any]:
    store = make_eval_store()
    runs = store.list_runs(limit=1)
    if not runs:
        return _evaluation_no_runs_surface()
    latest_run = runs[0]
    metrics_rows = store.get_metrics(str(latest_run.get("id") or ""))
    return _build_persisted_evaluation_surface(latest_run, metrics_rows)


def build_monitor_evaluation_dashboard_summary(payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or "unavailable")
    return {
        "evaluations_running": 1 if status == "running" else 0,
        "latest_evaluation": {
            "status": status,
            "kind": payload.get("kind"),
            "tone": payload.get("tone"),
            "headline": payload.get("headline"),
        },
    }


def get_monitor_evaluation_dashboard_summary() -> dict[str, Any]:
    return build_monitor_evaluation_dashboard_summary(get_monitor_evaluation_truth())


def _map_leases(rows: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    for row in rows:
        badge = _make_badge(row["desired_state"], row["observed_state"])
        triage = _classify_lease_triage(
            thread_id=row["thread_id"],
            badge=badge,
            observed_state=row["observed_state"],
            desired_state=row["desired_state"],
            updated_at=row["updated_at"],
        )
        items.append(
            {
                "lease_id": row["lease_id"],
                "provider": row["provider_name"],
                "instance_id": row["current_instance_id"],
                "thread": _thread_ref(row["thread_id"]),
                "state_badge": badge,
                "semantics": _classify_lease_semantics(thread_id=row["thread_id"], badge=badge),
                "triage": triage,
                "error": row["last_error"],
                "updated_at": row["updated_at"],
                "updated_ago": _format_time_ago(row["updated_at"]),
            }
        )

    summary = {key: 0 for key in LEASE_SEMANTIC_ORDER}
    for item in items:
        summary[item["semantics"]["category"]] += 1
    summary["total"] = len(items)

    groups = []
    for key in LEASE_SEMANTIC_ORDER:
        meta = LEASE_SEMANTIC_META[key]
        group_items = [item for item in items if item["semantics"]["category"] == key]
        groups.append(
            {
                "key": key,
                "title": meta["title"],
                "description": meta["description"],
                "count": len(group_items),
                "items": group_items,
            }
        )

    triage_summary = {key: 0 for key in LEASE_TRIAGE_ORDER}
    for item in items:
        triage_summary[item["triage"]["category"]] += 1
    triage_summary["total"] = len(items)

    triage_groups = []
    for key in LEASE_TRIAGE_ORDER:
        meta = LEASE_TRIAGE_META[key]
        group_items = [item for item in items if item["triage"]["category"] == key]
        triage_groups.append(
            {
                "key": key,
                "title": meta["title"],
                "description": meta["description"],
                "tone": meta["tone"],
                "count": len(group_items),
                "items": group_items,
            }
        )

    return {
        "title": "All Leases",
        "count": len(items),
        "summary": summary,
        "groups": groups,
        "triage": {
            "summary": triage_summary,
            "groups": triage_groups,
        },
        "items": items,
    }

def list_leases() -> dict[str, Any]:
    repo = make_sandbox_monitor_repo()
    try:
        return _map_leases(repo.query_leases())
    finally:
        repo.close()


def cleanup_resource_leases(
    *,
    action: str,
    lease_ids: list[str],
    expected_category: str,
) -> dict[str, Any]:
    if action != "cleanup_residue":
        raise ValueError(f"Unsupported cleanup action: {action}")
    if expected_category not in RESOURCE_CLEANUP_ALLOWED_CATEGORIES:
        raise ValueError("expected_category must be one of: detached_residue, orphan_cleanup")

    target_lease_ids = _cleanable_lease_ids(lease_ids)
    monitor_repo = make_sandbox_monitor_repo()
    lease_repo = make_lease_repo()
    chat_session_repo = make_chat_session_repo()
    try:
        rows_by_id = {str(row.get("lease_id") or ""): row for row in monitor_repo.query_leases() if row.get("lease_id")}
        providers, _ = init_providers_and_managers()
        cleaned: list[dict[str, Any]] = []
        skipped: list[str] = []
        errors: list[dict[str, Any]] = []

        for lease_id in target_lease_ids:
            row = rows_by_id.get(lease_id)
            if row is None:
                skipped.append(lease_id)
                errors.append({"lease_id": lease_id, "reason": "lease_not_found"})
                continue

            actual_category = _triage_category_for_row(row)
            if actual_category != expected_category:
                skipped.append(lease_id)
                errors.append(
                    {
                        "lease_id": lease_id,
                        "reason": "category_mismatch",
                        "expected_category": expected_category,
                        "actual_category": actual_category,
                    }
                )
                continue

            sessions = monitor_repo.query_lease_sessions(lease_id)
            live_session_ids = [
                str(session.get("chat_session_id"))
                for session in sessions
                if str(session.get("status") or "").strip().lower() in ACTIVE_CHAT_SESSION_STATUSES
            ]
            if live_session_ids:
                skipped.append(lease_id)
                errors.append(
                    {
                        "lease_id": lease_id,
                        "reason": "live_sessions_present",
                        "session_ids": live_session_ids,
                    }
                )
                continue

            if chat_session_repo.lease_has_running_command(lease_id):
                skipped.append(lease_id)
                errors.append({"lease_id": lease_id, "reason": "running_command_present"})
                continue

            provider_name = str(row.get("provider_name") or "").strip()
            instance_id = str(row.get("current_instance_id") or "").strip() or None
            if instance_id:
                provider = providers.get(provider_name)
                if provider is None:
                    skipped.append(lease_id)
                    errors.append(
                        {
                            "lease_id": lease_id,
                            "reason": "provider_unavailable",
                            "provider": provider_name,
                        }
                    )
                    continue
                if not provider.get_capability().can_destroy:
                    skipped.append(lease_id)
                    errors.append(
                        {
                            "lease_id": lease_id,
                            "reason": "provider_destroy_unsupported",
                            "provider": provider_name,
                        }
                    )
                    continue
                try:
                    destroyed = provider.destroy_session(instance_id, sync=True)
                except Exception as exc:
                    skipped.append(lease_id)
                    errors.append(
                        {
                            "lease_id": lease_id,
                            "reason": "provider_destroy_failed",
                            "provider": provider_name,
                            "detail": str(exc),
                        }
                    )
                    continue
                if not destroyed:
                    skipped.append(lease_id)
                    errors.append(
                        {
                            "lease_id": lease_id,
                            "reason": "provider_destroy_failed",
                            "provider": provider_name,
                            "detail": "destroy_session returned false",
                        }
                    )
                    continue

            lease_repo.delete(lease_id)
            cleaned.append({"lease_id": lease_id, "category": actual_category})

        refreshed_summary = list_leases()["triage"]["summary"]
        return {
            "action": action,
            "expected_category": expected_category,
            "attempted": target_lease_ids,
            "cleaned": cleaned,
            "skipped": skipped,
            "errors": errors,
            "refreshed_summary": refreshed_summary,
        }
    finally:
        chat_session_repo.close()
        lease_repo.close()
        monitor_repo.close()


# ---------------------------------------------------------------------------
# Public API: diagnostics
# ---------------------------------------------------------------------------


def runtime_health_snapshot() -> dict[str, Any]:
    """Lightweight control-plane health snapshot."""
    tables: dict[str, int] = {"chat_sessions": 0, "sandbox_leases": 0, "events": 0}
    storage_strategy = current_storage_strategy()

    if storage_strategy == "supabase":
        # @@@monitor-health-logical-counts - the API exposes logical control-plane counts, not provider-specific
        # physical table names. Supabase stores run events; SQLite still stores lease events.
        table_names = {
            "chat_sessions": "chat_sessions",
            "sandbox_leases": "sandbox_leases",
            "events": "run_events",
        }
        repo = make_sandbox_monitor_repo()
        try:
            raw_counts = repo.count_rows(list(table_names.values()))
        finally:
            repo.close()
        tables = {logical_name: int(raw_counts.get(table_name) or 0) for logical_name, table_name in table_names.items()}
        db_payload: dict[str, Any] = {
            "strategy": "supabase",
            "schema": str(os.getenv("LEON_DB_SCHEMA") or "public"),
            "counts": tables,
        }
    else:
        db_path = resolve_runtime_health_monitor_db_path()
        if db_path is None:
            raise RuntimeError("sqlite runtime health snapshot requires a sandbox db path")
        db_exists = db_path.exists()
        db_payload = {"path": str(db_path), "exists": db_exists, "counts": tables}
        if db_exists:
            table_names = {
                "chat_sessions": "chat_sessions",
                "sandbox_leases": "sandbox_leases",
                "events": "lease_events",
            }
            repo = make_runtime_health_monitor_repo()
            try:
                raw_counts = repo.count_rows(list(table_names.values()))
            finally:
                repo.close()
            tables = {logical_name: int(raw_counts.get(table_name) or 0) for logical_name, table_name in table_names.items()}
            db_payload["counts"] = tables

    _, managers = init_providers_and_managers()
    sessions = load_all_sessions(managers)
    provider_counts: dict[str, int] = {}
    for session in sessions:
        provider = str(session.get("provider") or "unknown")
        provider_counts[provider] = provider_counts.get(provider, 0) + 1

    return {
        "snapshot_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "db": db_payload,
        "sessions": {"total": len(sessions), "providers": provider_counts},
    }
