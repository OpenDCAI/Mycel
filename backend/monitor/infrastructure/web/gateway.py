"""Monitor backend boundary for routers and future service extraction."""

from __future__ import annotations

from typing import Any

from backend.monitor.application.use_cases import evaluation as monitor_evaluation
from backend.monitor.application.use_cases import provider_runtimes as monitor_provider_runtimes
from backend.monitor.application.use_cases import resources as monitor_resources
from backend.monitor.application.use_cases import sandbox_configs, sandbox_detail, sandbox_projection
from backend.monitor.application.use_cases import threads as monitor_threads
from backend.monitor.infrastructure.read_models import thread_read_service, thread_workbench_read_service, trace_read_service


def list_sandboxes() -> dict[str, Any]:
    return sandbox_projection.list_monitor_sandboxes()


def list_provider_orphan_runtimes() -> dict[str, Any]:
    return monitor_provider_runtimes.list_monitor_provider_orphan_runtimes()


def list_threads(app: Any, user_id: str) -> dict[str, Any]:
    return monitor_threads.list_monitor_threads(
        user_id,
        workbench_reader=thread_workbench_read_service.build_owner_thread_workbench_reader(app),
    )


def get_provider_detail(provider_id: str) -> dict[str, Any]:
    return monitor_provider_runtimes.get_monitor_provider_detail(provider_id)


def get_sandbox_detail(sandbox_id: str) -> dict[str, Any]:
    return sandbox_detail.get_monitor_sandbox_detail(sandbox_id)


def request_sandbox_cleanup(sandbox_id: str) -> dict[str, Any]:
    return sandbox_detail.request_monitor_sandbox_cleanup(sandbox_id)


def request_provider_orphan_runtime_cleanup(provider_id: str, runtime_id: str) -> dict[str, Any]:
    return monitor_provider_runtimes.request_monitor_provider_orphan_runtime_cleanup(provider_id, runtime_id)


def get_operation_detail(operation_id: str) -> dict[str, Any]:
    return sandbox_detail.get_monitor_operation_detail(operation_id)


def get_runtime_detail(runtime_id: str) -> dict[str, Any]:
    return monitor_provider_runtimes.get_monitor_runtime_detail(runtime_id)


def get_sandbox_configs() -> dict[str, Any]:
    return sandbox_configs.get_monitor_sandbox_configs()


async def get_thread_detail(app: Any, thread_id: str) -> dict[str, Any]:
    return await monitor_threads.get_monitor_thread_detail(
        thread_id,
        load_thread_base=thread_read_service.build_monitor_thread_base_loader(app),
        trace_reader=trace_read_service.build_monitor_trace_reader(app),
    )


def get_dashboard() -> dict[str, Any]:
    resources = get_resource_overview()
    sandboxes = list_sandboxes()
    evaluation = get_evaluation_workbench()

    resource_summary = resources.get("summary") or {}
    sandbox_summary = sandboxes.get("summary") or {}
    evaluation_overview = evaluation.get("overview") or {}
    latest_evaluation = evaluation.get("selected_run") or {}

    return {
        "snapshot_at": resource_summary.get("snapshot_at"),
        "infra": {
            "providers_active": int(resource_summary.get("active_providers") or 0),
            "providers_unavailable": int(resource_summary.get("unavailable_providers") or 0),
            "sandboxes_total": int(sandbox_summary.get("total") or sandboxes.get("count") or 0),
            "sandboxes_diverged": int(sandbox_summary.get("diverged") or 0) + int(sandbox_summary.get("orphan_diverged") or 0),
            "sandboxes_orphan": int(sandbox_summary.get("orphan") or 0) + int(sandbox_summary.get("orphan_diverged") or 0),
        },
        "workload": {
            "running_resource_rows": int(resource_summary.get("running_resource_rows") or 0),
            "evaluations_running": int(evaluation_overview.get("running_runs") or 0),
        },
        "latest_evaluation": {
            "run_id": latest_evaluation.get("run_id"),
            "status": latest_evaluation.get("status"),
            "headline": evaluation.get("summary") or "No evaluation runs recorded.",
        },
    }


def get_evaluation_workbench() -> dict[str, Any]:
    return monitor_evaluation.get_monitor_evaluation_workbench()


def get_evaluation_batches(*, limit: int = 50) -> dict[str, Any]:
    return monitor_evaluation.get_monitor_evaluation_batches(limit=limit)


def create_evaluation_batch(
    *,
    submitted_by_user_id: str,
    agent_user_id: str,
    scenario_ids: list[str],
    sandbox: str,
    max_concurrent: int,
) -> dict[str, Any]:
    return monitor_evaluation.create_monitor_evaluation_batch(
        submitted_by_user_id=submitted_by_user_id,
        agent_user_id=agent_user_id,
        scenario_ids=scenario_ids,
        sandbox=sandbox,
        max_concurrent=max_concurrent,
    )


def get_evaluation_scenarios() -> dict[str, Any]:
    return monitor_evaluation.get_monitor_evaluation_scenarios()


def start_evaluation_batch(
    *,
    batch_id: str,
    base_url: str,
    token: str,
    schedule_task,
) -> dict[str, Any]:
    return monitor_evaluation.start_monitor_evaluation_batch(
        batch_id=batch_id,
        base_url=base_url,
        token=token,
        schedule_task=schedule_task,
    )


def get_evaluation_batch_detail(batch_id: str) -> dict[str, Any]:
    return monitor_evaluation.get_monitor_evaluation_batch_detail(batch_id)


def get_evaluation_run_detail(run_id: str) -> dict[str, Any]:
    return monitor_evaluation.get_monitor_evaluation_run_detail(run_id)


def get_resource_overview() -> dict[str, Any]:
    return monitor_resources.get_monitor_resource_overview()


def refresh_resource_overview() -> dict[str, Any]:
    return monitor_resources.refresh_monitor_resource_overview()


def browse_sandbox(sandbox_id: str, path: str) -> dict[str, Any]:
    return monitor_resources.browse_monitor_sandbox(sandbox_id, path)


def read_sandbox(sandbox_id: str, path: str) -> dict[str, Any]:
    return monitor_resources.read_monitor_sandbox(sandbox_id, path)


def list_user_resource_providers(app: Any, user_id: str) -> dict[str, Any]:
    return monitor_resources.list_user_resource_providers(app, user_id)
