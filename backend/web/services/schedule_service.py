"""Agent schedule CRUD service."""

from __future__ import annotations

from typing import Any

from storage.runtime import build_schedule_repo as make_schedule_repo

_RUN_TRIGGERS = {"scheduler", "manual"}
_RUN_STATUSES = {"queued", "running", "succeeded", "failed", "cancelled"}


def _require_non_empty(name: str, value: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _validate_schedule_target(target_thread_id: str | None, create_thread_on_run: bool) -> None:
    if not target_thread_id and not create_thread_on_run:
        raise ValueError("schedule target must set target_thread_id or create_thread_on_run")


def list_schedules(owner_user_id: str) -> list[dict[str, Any]]:
    _require_non_empty("owner_user_id", owner_user_id)
    repo = make_schedule_repo()
    try:
        return repo.list_by_owner(owner_user_id)
    finally:
        repo.close()


def get_schedule(schedule_id: str) -> dict[str, Any] | None:
    _require_non_empty("schedule_id", schedule_id)
    repo = make_schedule_repo()
    try:
        return repo.get(schedule_id)
    finally:
        repo.close()


def create_schedule(
    *,
    owner_user_id: str,
    agent_user_id: str,
    cron_expression: str,
    instruction_template: str,
    target_thread_id: str | None = None,
    create_thread_on_run: bool = False,
    enabled: bool = True,
    timezone: str = "UTC",
    next_run_at: str | None = None,
) -> dict[str, Any]:
    _require_non_empty("owner_user_id", owner_user_id)
    _require_non_empty("agent_user_id", agent_user_id)
    _require_non_empty("cron_expression", cron_expression)
    _require_non_empty("instruction_template", instruction_template)
    _require_non_empty("timezone", timezone)
    _validate_schedule_target(target_thread_id, create_thread_on_run)
    repo = make_schedule_repo()
    try:
        return repo.create(
            owner_user_id=owner_user_id,
            agent_user_id=agent_user_id,
            cron_expression=cron_expression,
            instruction_template=instruction_template,
            target_thread_id=target_thread_id,
            create_thread_on_run=create_thread_on_run,
            enabled=enabled,
            timezone=timezone,
            next_run_at=next_run_at,
        )
    finally:
        repo.close()


def update_schedule(schedule_id: str, **fields: Any) -> dict[str, Any] | None:
    _require_non_empty("schedule_id", schedule_id)
    if "create_thread_on_run" in fields or "target_thread_id" in fields:
        _validate_schedule_target(fields.get("target_thread_id"), bool(fields.get("create_thread_on_run")))
    for key in ("agent_user_id", "cron_expression", "instruction_template", "timezone"):
        if key in fields and fields[key] is not None:
            _require_non_empty(key, fields[key])
    repo = make_schedule_repo()
    try:
        return repo.update(schedule_id, **fields)
    finally:
        repo.close()


def delete_schedule(schedule_id: str) -> bool:
    _require_non_empty("schedule_id", schedule_id)
    repo = make_schedule_repo()
    try:
        return repo.delete(schedule_id)
    finally:
        repo.close()


def create_schedule_run(
    *,
    schedule_id: str,
    owner_user_id: str,
    agent_user_id: str,
    triggered_by: str,
    thread_id: str | None = None,
    scheduled_for: str | None = None,
    input_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _require_non_empty("schedule_id", schedule_id)
    _require_non_empty("owner_user_id", owner_user_id)
    _require_non_empty("agent_user_id", agent_user_id)
    if triggered_by not in _RUN_TRIGGERS:
        raise ValueError("triggered_by must be scheduler or manual")
    repo = make_schedule_repo()
    try:
        return repo.create_run(
            schedule_id=schedule_id,
            owner_user_id=owner_user_id,
            agent_user_id=agent_user_id,
            triggered_by=triggered_by,
            thread_id=thread_id,
            scheduled_for=scheduled_for,
            input_json=input_json,
        )
    finally:
        repo.close()


def get_schedule_run(run_id: str) -> dict[str, Any] | None:
    _require_non_empty("run_id", run_id)
    repo = make_schedule_repo()
    try:
        return repo.get_run(run_id)
    finally:
        repo.close()


def list_schedule_runs(schedule_id: str) -> list[dict[str, Any]]:
    _require_non_empty("schedule_id", schedule_id)
    repo = make_schedule_repo()
    try:
        return repo.list_runs(schedule_id)
    finally:
        repo.close()


def update_schedule_run(run_id: str, **fields: Any) -> dict[str, Any] | None:
    _require_non_empty("run_id", run_id)
    if "status" in fields and fields["status"] not in _RUN_STATUSES:
        raise ValueError("status must be queued, running, succeeded, failed, or cancelled")
    repo = make_schedule_repo()
    try:
        return repo.update_run(run_id, **fields)
    finally:
        repo.close()


def delete_schedule_run(run_id: str) -> bool:
    _require_non_empty("run_id", run_id)
    repo = make_schedule_repo()
    try:
        return repo.delete_run(run_id)
    finally:
        repo.close()
