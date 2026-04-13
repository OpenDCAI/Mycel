"""Runtime trigger path for agent schedules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.web.services import schedule_service
from backend.web.services.message_routing import TargetThreadActiveError, route_message_to_brain
from core.runtime.middleware.monitor import AgentState


class TargetThreadBusyError(RuntimeError):
    """Raised when a schedule trigger needs a fresh run but the target is active."""


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _schedule_instruction(schedule: dict[str, Any], run_id: str) -> str:
    return f"[Scheduled instruction]\nSchedule ID: {schedule['id']}\nSchedule Run ID: {run_id}\n\n{schedule['instruction_template']}"


def _target_thread(schedule: dict[str, Any]) -> str:
    thread_id = schedule.get("target_thread_id")
    if not thread_id:
        raise ValueError("schedule trigger requires target_thread_id in 02I")
    return str(thread_id)


def _validate_thread(app: Any, schedule: dict[str, Any], thread_id: str, owner_user_id: str) -> None:
    thread = app.state.thread_repo.get_by_id(thread_id)
    if thread is None:
        raise ValueError(f"target thread {thread_id} not found")
    if thread.get("owner_user_id") != owner_user_id:
        raise PermissionError("target thread is not owned by schedule owner")
    if thread.get("member_id") != schedule.get("agent_user_id"):
        raise ValueError("target thread agent does not match schedule agent")


def _thread_is_active(app: Any, thread_id: str) -> bool:
    thread = app.state.thread_repo.get_by_id(thread_id)
    sandbox_type = (thread or {}).get("sandbox_type", "local")
    agent = getattr(app.state, "agent_pool", {}).get(f"{thread_id}:{sandbox_type}")
    runtime = getattr(agent, "runtime", None)
    return bool(runtime and getattr(runtime, "current_state", None) == AgentState.ACTIVE)


def _validate_schedule(schedule: dict[str, Any] | None, owner_user_id: str) -> dict[str, Any]:
    if schedule is None:
        raise ValueError("schedule not found")
    if schedule.get("owner_user_id") != owner_user_id:
        raise PermissionError("schedule is not owned by current user")
    if not schedule.get("enabled", True):
        raise ValueError("schedule is disabled")
    return schedule


async def trigger_schedule(
    app: Any,
    schedule_id: str,
    *,
    owner_user_id: str,
    triggered_by: str = "manual",
) -> dict[str, Any]:
    schedule = _validate_schedule(schedule_service.get_schedule(schedule_id), owner_user_id)
    thread_id = _target_thread(schedule)
    _validate_thread(app, schedule, thread_id, owner_user_id)
    if _thread_is_active(app, thread_id):
        raise TargetThreadBusyError("target thread is already active")

    run = schedule_service.create_schedule_run(
        schedule_id=schedule["id"],
        owner_user_id=owner_user_id,
        agent_user_id=schedule["agent_user_id"],
        triggered_by=triggered_by,
        thread_id=thread_id,
        input_json={"instruction_template": schedule["instruction_template"]},
    )
    try:
        routing = await route_message_to_brain(
            app,
            thread_id,
            _schedule_instruction(schedule, run["id"]),
            source="schedule",
            require_new_run=True,
            extra_message_metadata={"schedule_run_id": run["id"]},
        )
    except TargetThreadActiveError as exc:
        schedule_service.update_schedule_run(
            run["id"],
            status="cancelled",
            completed_at=_now_iso(),
            error=str(exc),
        )
        raise TargetThreadBusyError(str(exc)) from exc
    except Exception as exc:
        schedule_service.update_schedule_run(
            run["id"],
            status="failed",
            completed_at=_now_iso(),
            error=str(exc),
        )
        raise

    updated_run = schedule_service.update_schedule_run(
        run["id"],
        status="running",
        thread_id=thread_id,
        started_at=_now_iso(),
        output_json={"routing": routing},
    )
    schedule_service.update_schedule(schedule["id"], last_run_at=_now_iso())
    return {"schedule_run": updated_run or run, "routing": routing}
