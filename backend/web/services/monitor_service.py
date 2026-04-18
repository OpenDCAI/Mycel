"""Monitor service: sandbox observation + health diagnostics."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from backend.web.core import config as web_config
from backend.web.services import monitor_operation_service, sandbox_service
from backend.web.services.resource_common import thread_owners as _thread_owners
from backend.web.services.thread_visibility import canonical_owner_threads
from eval.batch_executor import EvaluationBatchExecutor
from eval.batch_service import EvaluationBatchService
from eval.harness.client import EvalClient
from eval.harness.runner import EvalRunner
from eval.harness.scenario import load_scenarios_from_dir
from eval.models import EvalScenario
from eval.storage import TrajectoryStore
from storage.runtime import build_evaluation_batch_repo, build_thread_repo
from storage.runtime import build_sandbox_monitor_repo as make_sandbox_monitor_repo

# ---------------------------------------------------------------------------
# Mapping helpers (private)
# ---------------------------------------------------------------------------
EVAL_SCENARIO_DIR = Path(__file__).resolve().parents[3] / "eval" / "scenarios"


def make_eval_batch_service() -> EvaluationBatchService:
    return EvaluationBatchService(batch_repo=build_evaluation_batch_repo())


def list_monitor_threads(app: Any, user_id: str) -> dict[str, Any]:
    from backend.web.routers.threads import build_owner_thread_workbench

    return build_owner_thread_workbench(app, user_id)


def get_monitor_sandbox_configs() -> dict[str, Any]:
    providers = sandbox_service.available_sandbox_types()
    return {
        "source": "runtime_sandbox_inventory",
        "default_local_cwd": str(web_config.LOCAL_WORKSPACE_ROOT),
        "count": len(providers),
        "providers": providers,
    }


def get_resource_overview_snapshot() -> dict[str, Any]:
    from backend.web.services.resource_cache import get_resource_overview_snapshot as _get_resource_overview_snapshot

    return _get_resource_overview_snapshot()


def _format_time_ago(iso_timestamp: str | None) -> str:
    dt = _parse_local_timestamp(iso_timestamp)
    if dt is None:
        return "never"
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


def _canonical_live_thread_refs(raw_thread_ids: list[str]) -> list[dict[str, Any]]:
    live_threads = _live_thread_ids(raw_thread_ids)
    if not live_threads:
        return []

    repo = build_thread_repo()
    try:
        rows = repo.list_by_ids([thread_id for thread_id in raw_thread_ids if thread_id in live_threads])
    finally:
        repo.close()

    canonical = canonical_owner_threads(rows)
    return [{"thread_id": str(row.get("id") or "").strip()} for row in canonical if str(row.get("id") or "").strip()]


def _derive_thread_summary_from_sessions(sessions: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not sessions:
        return None
    latest = sessions[0]
    summary = {
        "sandbox_id": latest.get("sandbox_id"),
        "provider_name": latest.get("provider_name"),
        "current_instance_id": latest.get("current_instance_id"),
        "desired_state": latest.get("desired_state"),
        "observed_state": latest.get("observed_state"),
    }
    return summary if any(value is not None for value in summary.values()) else None


def _normalize_thread_summary(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    payload = {
        "sandbox_id": summary.get("sandbox_id"),
        "provider_name": summary.get("provider_name"),
        "current_instance_id": summary.get("current_instance_id"),
        "desired_state": summary.get("desired_state"),
        "observed_state": summary.get("observed_state"),
    }
    return payload if any(value is not None for value in payload.values()) else None


def _normalize_thread_owner(owner: dict[str, Any] | None) -> dict[str, Any] | None:
    if owner is None:
        return None
    return {
        "user_id": owner.get("user_id") or owner.get("agent_user_id"),
        "display_name": owner.get("display_name") or owner.get("agent_name"),
        "email": owner.get("email"),
        "avatar_url": owner.get("avatar_url"),
    }


def _normalize_monitor_thread(thread: dict[str, Any], requested_thread_id: str) -> dict[str, Any]:
    return {
        **thread,
        "thread_id": thread.get("thread_id") or thread.get("id") or requested_thread_id,
    }


def _live_thread_ids(thread_ids: list[str]) -> set[str]:
    unique = sorted({str(thread_id or "").strip() for thread_id in thread_ids if str(thread_id or "").strip()})
    if not unique:
        return set()
    # @@@monitor-live-thread-state - monitor triage must validate terminal pointers against live
    # thread rows, otherwise stale abstract_terminals residue gets misclassified as healthy.
    owners = _thread_owners(unique)
    return {thread_id for thread_id in unique if (owners.get(thread_id) or {}).get("agent_user_id")}


SANDBOX_SEMANTIC_ORDER = [
    "orphan_diverged",
    "diverged",
    "orphan",
    "healthy",
]

SANDBOX_SEMANTIC_META = {
    "orphan_diverged": {
        "title": "Orphaned + Diverged",
        "description": "Sandbox lost thread binding while desired and observed state still disagree.",
    },
    "diverged": {
        "title": "Diverged",
        "description": "Sandbox is still attached to a thread, but runtime state has not converged.",
    },
    "orphan": {
        "title": "Orphans",
        "description": "Sandbox has no active thread binding. Usually cleanup or historical residue.",
    },
    "healthy": {
        "title": "Healthy",
        "description": "Sandbox has a thread binding and desired state matches observed state.",
    },
}


SANDBOX_TRIAGE_ORDER = [
    "active_drift",
    "detached_residue",
    "orphan_cleanup",
    "healthy_capacity",
]

SANDBOX_TRIAGE_META = {
    "active_drift": {
        "title": "Active Drift",
        "description": "Sandboxes whose desired and observed state still disagree recently enough to warrant attention.",
        "tone": "warning",
    },
    "detached_residue": {
        "title": "Detached Residue",
        "description": (
            "Sandboxes still marked desired=running but observed=detached long after the runtime "
            "stopped moving. Usually cleanup debt, not live pressure."
        ),
        "tone": "danger",
    },
    "orphan_cleanup": {
        "title": "Orphan Cleanup",
        "description": "Sandboxes that have already lost thread binding and mainly represent cleanup backlog or historical residue.",
        "tone": "warning",
    },
    "healthy_capacity": {
        "title": "Healthy Capacity",
        "description": "Sandboxes with attached thread context and converged runtime state.",
        "tone": "success",
    },
}

DETACHED_RESIDUE_THRESHOLD_HOURS = 4.0


def _classify_sandbox_semantics(*, thread_id: str | None, badge: dict[str, Any]) -> dict[str, str]:
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
    meta = SANDBOX_SEMANTIC_META[category]
    return {
        "category": category,
        "title": meta["title"],
        "description": meta["description"],
    }


def _parse_local_timestamp(iso_timestamp: str | None) -> datetime | None:
    if not iso_timestamp:
        return None
    # @@@naive-local-time - SQLite timestamps in this module are local-time strings.
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


def _classify_sandbox_triage(
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

    meta = SANDBOX_TRIAGE_META[key]
    return {
        "category": key,
        "title": meta["title"],
        "description": meta["description"],
        "tone": meta["tone"],
        "age_hours": age_hours,
    }


def _sandbox_groups(
    *,
    items: list[dict[str, Any]],
    order: list[str],
    meta_by_key: dict[str, dict[str, Any]],
    field: str,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    summary = {key: 0 for key in order}
    for item in items:
        summary[item[field]["category"]] += 1
    summary["total"] = len(items)

    groups = []
    for key in order:
        meta = meta_by_key[key]
        group_items = [item for item in items if item[field]["category"] == key]
        groups.append({"key": key, **meta, "count": len(group_items), "items": group_items})
    return summary, groups


def _build_monitor_evaluation_run_fact_rows(metrics_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    metrics_by_tier = {str(row.get("tier") or "").strip().lower(): row.get("metrics") or {} for row in metrics_rows}
    system_metrics = metrics_by_tier.get("system") or {}
    objective_metrics = metrics_by_tier.get("objective") or {}
    facts = [{"label": "Metric Tiers", "value": str(len(metrics_rows))}]
    for label, key in [
        ("Total tokens", "total_tokens"),
        ("LLM calls", "llm_call_count"),
        ("Tool calls", "tool_call_count"),
    ]:
        value = system_metrics.get(key)
        if value is not None:
            facts.append({"label": label, "value": str(value)})
    total_duration_ms = objective_metrics.get("total_duration_ms")
    if total_duration_ms is not None:
        duration_value = int(total_duration_ms) if float(total_duration_ms).is_integer() else total_duration_ms
        facts.append({"label": "Duration (ms)", "value": str(duration_value)})
    return facts


def _build_monitor_evaluation_run_row(run: dict[str, Any], metrics_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "run_id": str(run.get("id") or "") or None,
        "thread_id": str(run.get("thread_id") or "") or None,
        "status": str(run.get("status") or "") or None,
        "started_at": str(run.get("started_at") or "") or None,
        "finished_at": str(run.get("finished_at") or "") or None,
        "user_message": str(run.get("user_message") or "") or None,
        "facts": _build_monitor_evaluation_run_fact_rows(metrics_rows),
    }


def get_monitor_evaluation_workbench() -> dict[str, Any]:
    store = TrajectoryStore()
    runs = store.list_runs(limit=25)
    if not runs:
        return {
            "headline": "Evaluation Workbench",
            "summary": "No persisted evaluation runs are available yet.",
            "overview": {
                "total_runs": 0,
                "running_runs": 0,
                "completed_runs": 0,
                "failed_runs": 0,
            },
            "runs": [],
            "selected_run": None,
            "limitations": ["Create and start an evaluation batch to populate persisted runs."],
        }

    run_rows = []
    running_runs = 0
    completed_runs = 0
    failed_runs = 0
    for run in runs:
        status = str(run.get("status") or "").strip().lower()
        if status == "running":
            running_runs += 1
        elif status == "completed":
            completed_runs += 1
        elif status in {"error", "failed", "cancelled"}:
            failed_runs += 1
        run_rows.append(_build_monitor_evaluation_run_row(run, store.get_metrics(str(run.get("id") or ""))))

    return {
        "headline": "Evaluation Workbench",
        "summary": "Recent persisted evaluation runs and their runtime state.",
        "overview": {
            "total_runs": len(run_rows),
            "running_runs": running_runs,
            "completed_runs": completed_runs,
            "failed_runs": failed_runs,
        },
        "runs": run_rows,
        "selected_run": run_rows[0],
        "limitations": [],
    }


def get_monitor_evaluation_run_detail(run_id: str) -> dict[str, Any]:
    store = TrajectoryStore()
    run = store.get_run(run_id)
    if run is None:
        raise KeyError(f"Evaluation run not found: {run_id}")
    run_row = _build_monitor_evaluation_run_row(run, store.get_metrics(run_id))
    detail = {"run": run_row, "facts": run_row["facts"], "limitations": []}
    detail["batch_run"] = make_eval_batch_service().get_batch_run_for_eval_run(run_id)
    return detail


def get_monitor_evaluation_batches(limit: int = 50) -> dict[str, Any]:
    items = make_eval_batch_service().list_batches(limit=limit)
    return {
        "items": items,
        "count": len(items),
    }


def get_monitor_evaluation_scenarios() -> dict[str, Any]:
    items = [
        {
            "scenario_id": scenario.id,
            "name": scenario.name,
            "category": scenario.category,
            "sandbox": scenario.sandbox,
            "message_count": len(scenario.messages),
            "timeout_seconds": scenario.timeout_seconds,
        }
        for scenario in load_scenarios_from_dir(EVAL_SCENARIO_DIR)
    ]
    return {"items": items, "count": len(items)}


def create_monitor_evaluation_batch(
    *,
    submitted_by_user_id: str,
    agent_user_id: str,
    scenario_ids: list[str],
    sandbox: str,
    max_concurrent: int,
) -> dict[str, Any]:
    batch = make_eval_batch_service().create_batch(
        submitted_by_user_id=submitted_by_user_id,
        agent_user_id=agent_user_id,
        scenario_ids=scenario_ids,
        sandbox=sandbox,
        max_concurrent=max_concurrent,
    )
    return {"batch": batch}


def _select_eval_scenarios(scenario_ids: list[str], *, sandbox: str) -> list[EvalScenario]:
    catalog = {scenario.id: scenario for scenario in load_scenarios_from_dir(EVAL_SCENARIO_DIR)}
    missing = [scenario_id for scenario_id in scenario_ids if scenario_id not in catalog]
    if missing:
        raise KeyError(f"Evaluation scenarios not found: {', '.join(missing)}")
    return [catalog[scenario_id].model_copy(update={"sandbox": sandbox}) for scenario_id in scenario_ids]


async def _run_monitor_evaluation_batch(
    *,
    batch_id: str,
    scenarios: list[EvalScenario],
    base_url: str,
    token: str,
    agent_user_id: str,
    batch_service: EvaluationBatchService,
) -> None:
    client = EvalClient(base_url=base_url, token=token)
    try:
        runner = EvalRunner(client=client, agent_user_id=agent_user_id, store=TrajectoryStore())
        executor = EvaluationBatchExecutor(runner=runner, batch_service=batch_service)
        await executor.run_batch(batch_id, scenarios)
    finally:
        await client.close()


def start_monitor_evaluation_batch(
    batch_id: str,
    *,
    base_url: str,
    token: str,
    schedule_task,
) -> dict[str, Any]:
    batch_service = make_eval_batch_service()
    detail = batch_service.get_batch_detail(batch_id)
    batch = detail["batch"]
    config = batch.get("config_json") or {}
    scenario_ids = config.get("scenario_ids")
    sandbox = config.get("sandbox")
    agent_user_id = batch.get("agent_user_id")
    if not scenario_ids:
        raise ValueError("Evaluation batch is missing scenario_ids")
    if not sandbox:
        raise ValueError("Evaluation batch is missing sandbox")
    if not agent_user_id:
        raise ValueError("Evaluation batch is missing agent_user_id")
    scenarios = _select_eval_scenarios(
        [str(scenario_id) for scenario_id in scenario_ids],
        sandbox=str(sandbox),
    )
    updated = batch_service.update_batch_status(batch_id, "running")
    schedule_task(
        _run_monitor_evaluation_batch,
        batch_id=batch_id,
        scenarios=scenarios,
        base_url=base_url.rstrip("/"),
        token=token,
        agent_user_id=str(agent_user_id),
        batch_service=batch_service,
    )
    return {"accepted": True, "batch": updated}


def get_monitor_evaluation_batch_detail(batch_id: str) -> dict[str, Any]:
    return make_eval_batch_service().get_batch_detail(batch_id)


def _map_monitor_sandboxes(rows: list[dict[str, Any]], *, title: str) -> dict[str, Any]:
    live_threads = _live_thread_ids([str(row.get("thread_id") or "").strip() for row in rows])
    items = []
    for row in rows:
        thread_id = str(row.get("thread_id") or "").strip() or None
        if thread_id not in live_threads:
            thread_id = None
        badge = _make_badge(row["desired_state"], row["observed_state"])
        triage = _classify_sandbox_triage(
            thread_id=thread_id,
            badge=badge,
            observed_state=row["observed_state"],
            desired_state=row["desired_state"],
            updated_at=row["updated_at"],
        )
        item = {
            "sandbox_id": row.get("sandbox_id"),
            "provider": row["provider_name"],
            "instance_id": row["current_instance_id"],
            "thread": _thread_ref(thread_id),
            "state_badge": badge,
            "semantics": _classify_sandbox_semantics(thread_id=thread_id, badge=badge),
            "triage": triage,
            "error": row["last_error"],
            "updated_at": row["updated_at"],
            "updated_ago": _format_time_ago(row["updated_at"]),
        }
        items.append(item)

    summary, groups = _sandbox_groups(
        items=items,
        order=SANDBOX_SEMANTIC_ORDER,
        meta_by_key=SANDBOX_SEMANTIC_META,
        field="semantics",
    )
    triage_summary, triage_groups = _sandbox_groups(
        items=items,
        order=SANDBOX_TRIAGE_ORDER,
        meta_by_key=SANDBOX_TRIAGE_META,
        field="triage",
    )

    return {
        "source": "sandbox_canonical",
        "title": title,
        "count": len(items),
        "summary": summary,
        "groups": groups,
        "triage": {
            "summary": triage_summary,
            "groups": triage_groups,
        },
        "items": items,
    }


def list_monitor_sandboxes() -> dict[str, Any]:
    repo = make_sandbox_monitor_repo()
    try:
        return _map_monitor_sandboxes(repo.query_sandboxes(), title="All Sandboxes")
    finally:
        repo.close()


def list_monitor_provider_orphan_runtimes() -> dict[str, Any]:
    _, managers = sandbox_service.init_providers_and_managers()
    runtimes = []
    for item in sandbox_service.load_provider_orphan_sessions(managers):
        runtimes.append(
            {
                "runtime_id": str(item.get("session_id") or ""),
                "provider": str(item.get("provider") or ""),
                "status": str(item.get("status") or "unknown"),
                "source": "provider_orphan",
            }
        )
    return {"count": len(runtimes), "runtimes": runtimes}


def _build_monitor_sandbox_detail(repo: Any, sandbox_id: str) -> dict[str, Any]:
    sandbox = repo.query_sandbox(sandbox_id)
    if sandbox is None:
        raise KeyError(f"Sandbox not found: {sandbox_id}")
    cleanup_target = repo.query_sandbox_cleanup_target(sandbox_id) or {}

    threads = repo.query_sandbox_threads(sandbox_id)
    sessions = repo.query_sandbox_sessions(sandbox_id)
    runtime_session_id = repo.query_sandbox_instance_id(sandbox_id)

    raw_thread_ids = [str(item.get("thread_id") or "").strip() for item in threads if str(item.get("thread_id") or "").strip()]
    live_thread_refs = _canonical_live_thread_refs(raw_thread_ids)
    badge = _make_badge(sandbox.get("desired_state"), sandbox.get("observed_state"))
    triage = _classify_sandbox_triage(
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
        "sessions": [
            {
                "chat_session_id": item.get("chat_session_id"),
                "thread_id": item.get("thread_id"),
                "status": item.get("status"),
                "started_at": item.get("started_at"),
                "ended_at": item.get("ended_at"),
                "close_reason": item.get("close_reason"),
            }
            for item in sessions
        ],
        "cleanup": _sandbox_detail_cleanup_truth(
            sandbox_id=str(sandbox.get("sandbox_id") or "").strip(),
            cleanup_target=cleanup_target,
            triage=triage,
            provider_name=provider_name,
            runtime_session_id=runtime_session_id,
            sessions=[
                {
                    "chat_session_id": item.get("chat_session_id"),
                    "thread_id": item.get("thread_id"),
                    "status": item.get("status"),
                    "started_at": item.get("started_at"),
                    "ended_at": item.get("ended_at"),
                    "close_reason": item.get("close_reason"),
                }
                for item in sessions
            ],
            threads=live_thread_refs,
        ),
    }


def _sandbox_detail_cleanup_truth(
    *,
    sandbox_id: str,
    cleanup_target: dict[str, Any],
    triage: dict[str, Any],
    provider_name: str,
    runtime_session_id: str | None,
    sessions: list[dict[str, Any]],
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
        runtime_session_id=runtime_session_id,
        sessions=sessions,
        threads=threads,
    )


def get_monitor_sandbox_detail(sandbox_id: str) -> dict[str, Any]:
    repo = make_sandbox_monitor_repo()
    try:
        return {
            "source": "sandbox_canonical",
            **_build_monitor_sandbox_detail(repo, sandbox_id),
        }
    finally:
        repo.close()


def get_monitor_provider_detail(provider_id: str) -> dict[str, Any]:
    snapshot = get_resource_overview_snapshot()
    providers = snapshot.get("providers") or []
    provider = next((item for item in providers if str(item.get("id") or "") == provider_id), None)
    if provider is None:
        raise KeyError(f"Provider not found: {provider_id}")

    resource_rows = provider.get("sessions") or []
    return {
        "provider": provider,
        "sandbox_ids": _resource_row_values(resource_rows, "sandboxId"),
        "runtime_session_ids": _resource_row_values(resource_rows, "runtimeSessionId"),
    }


def _resource_row_values(resource_rows: list[dict[str, Any]], key: str) -> list[str]:
    return sorted({str(item.get(key) or "").strip() for item in resource_rows if str(item.get(key) or "").strip()})


def get_monitor_runtime_detail(runtime_session_id: str) -> dict[str, Any]:
    snapshot = get_resource_overview_snapshot()
    for provider in snapshot.get("providers") or []:
        for session in provider.get("sessions") or []:
            current = str(session.get("runtimeSessionId") or "").strip()
            if current != runtime_session_id:
                continue
            return {
                "provider": {
                    "id": provider.get("id"),
                    "name": provider.get("name"),
                    "status": provider.get("status"),
                    "consoleUrl": provider.get("consoleUrl"),
                },
                "runtime": session,
                "sandbox_id": session.get("sandboxId"),
                "thread_id": session.get("threadId"),
            }
    raise KeyError(f"Runtime not found: {runtime_session_id}")


async def get_monitor_thread_detail(app: Any, thread_id: str) -> dict[str, Any]:
    from backend.web.services.monitor_trace_service import build_monitor_thread_trajectory

    thread_repo = getattr(app.state, "thread_repo", None)
    if thread_repo is None:
        raise RuntimeError("thread_repo is required for monitor thread detail")

    thread = thread_repo.get_by_id(thread_id)
    if thread is None:
        raise KeyError(f"Thread not found: {thread_id}")

    repo = make_sandbox_monitor_repo()
    try:
        summary = repo.query_thread_summary(thread_id)
        sessions = repo.query_thread_sessions(thread_id)
    finally:
        repo.close()

    if summary is None:
        summary = _derive_thread_summary_from_sessions(sessions)
    summary = _normalize_thread_summary(summary)

    owners = _thread_owners(
        [thread_id],
        user_repo=getattr(app.state, "user_repo", None),
        thread_repo=thread_repo,
    )

    return {
        "thread": _normalize_monitor_thread(thread, thread_id),
        "owner": _normalize_thread_owner(owners.get(thread_id)),
        "summary": summary,
        "sessions": sessions,
        "trajectory": await build_monitor_thread_trajectory(app, thread_id),
    }


def request_monitor_sandbox_cleanup(sandbox_id: str) -> dict[str, Any]:
    payload = get_monitor_sandbox_detail(sandbox_id)
    sandbox = payload["sandbox"]
    provider = payload.get("provider") or {}
    runtime = payload.get("runtime") or {}
    threads = payload.get("threads") or []

    cleanup_target = _sandbox_cleanup_target(sandbox_id)
    lower_runtime_handle = str(cleanup_target.get("lower_runtime_handle") or "").strip()
    sandbox_detail = {
        "sandbox": sandbox,
        "lower_runtime": {"handle": lower_runtime_handle},
        "triage": payload.get("triage"),
        "provider": provider,
        "runtime": runtime,
        "threads": threads,
        "sessions": payload.get("sessions") or [],
        "cleanup": monitor_operation_service.build_sandbox_cleanup_truth(
            sandbox_id=sandbox_id,
            triage=payload.get("triage"),
            provider_name=str(provider.get("id") or sandbox.get("provider_name") or ""),
            runtime_session_id=str(runtime.get("runtime_session_id") or ""),
            sessions=payload.get("sessions") or [],
            threads=threads,
        ),
    }
    return monitor_operation_service.request_sandbox_cleanup(sandbox_detail)


def request_monitor_provider_orphan_runtime_cleanup(provider_name: str, runtime_id: str) -> dict[str, Any]:
    provider = str(provider_name or "").strip()
    runtime = str(runtime_id or "").strip()
    for item in list_monitor_provider_orphan_runtimes().get("runtimes", []):
        if str(item.get("provider") or "").strip() == provider and str(item.get("runtime_id") or "").strip() == runtime:
            session_truth = {**item, "session_id": runtime}
            return monitor_operation_service.request_provider_orphan_runtime_cleanup(provider, runtime, session_truth)
    raise KeyError(f"Provider orphan runtime not found: {provider}:{runtime}")


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


# ---------------------------------------------------------------------------
# Public API: diagnostics
# ---------------------------------------------------------------------------
