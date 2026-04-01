"""Pydantic models for panel API (Members, Tasks, Library, Profile)."""

import json
from typing import Literal

from croniter import croniter
from pydantic import BaseModel, field_validator


def _check_cron_expr(v: str | None) -> str | None:
    if v is not None and not croniter.is_valid(v):
        raise ValueError(f"Invalid cron expression: {v!r}")
    return v


def _check_json_template(v: str | None) -> str | None:
    if v is not None:
        try:
            json.loads(v)
        except (json.JSONDecodeError, TypeError):
            raise ValueError("task_template must be valid JSON")
    return v


# ── Members ──


class MemberConfigPayload(BaseModel):
    prompt: str | None = None
    rules: list[dict] | None = None
    tools: list[dict] | None = None
    mcps: list[dict] | None = None
    skills: list[dict] | None = None
    subAgents: list[dict] | None = None  # noqa: N815


class CreateMemberRequest(BaseModel):
    name: str
    description: str = ""


class UpdateMemberRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


class PublishMemberRequest(BaseModel):
    bump_type: str = "patch"  # patch | minor | major
    notes: str = ""


# ── Tasks ──


class CreateTaskRequest(BaseModel):
    title: str = "新任务"
    description: str = ""
    assignee_id: str = ""
    priority: Literal["high", "medium", "low"] = "medium"
    deadline: str = ""
    tags: list[str] = []


class UpdateTaskRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    assignee_id: str | None = None
    status: Literal["pending", "running", "completed", "failed"] | None = None
    priority: Literal["high", "medium", "low"] | None = None
    progress: int | None = None
    deadline: str | None = None
    tags: list[str] | None = None


class BulkTaskStatusRequest(BaseModel):
    ids: list[str]
    status: Literal["pending", "running", "completed", "failed"]


class BulkDeleteTasksRequest(BaseModel):
    ids: list[str]


# ── Library ──


class CreateResourceRequest(BaseModel):
    name: str
    desc: str = ""
    provider_type: str | None = None
    features: dict[str, bool] | None = None


class UpdateResourceRequest(BaseModel):
    name: str | None = None
    desc: str | None = None
    features: dict[str, bool] | None = None


class UpdateResourceContentRequest(BaseModel):
    content: str


# ── Profile ──


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    initials: str | None = None
    email: str | None = None


# ── Cron Jobs ──


class CreateCronJobRequest(BaseModel):
    name: str
    description: str = ""
    cron_expression: str
    task_template: str = "{}"
    enabled: bool = True

    @field_validator("cron_expression")
    @classmethod
    def validate_cron_expression(cls, v: str) -> str:
        return _check_cron_expr(v)  # type: ignore[return-value]

    @field_validator("task_template")
    @classmethod
    def validate_task_template(cls, v: str) -> str:
        return _check_json_template(v)  # type: ignore[return-value]


class UpdateCronJobRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    cron_expression: str | None = None
    task_template: str | None = None
    enabled: bool | None = None

    @field_validator("cron_expression")
    @classmethod
    def validate_cron_expression(cls, v: str | None) -> str | None:
        return _check_cron_expr(v)

    @field_validator("task_template")
    @classmethod
    def validate_task_template(cls, v: str | None) -> str | None:
        return _check_json_template(v)


# ── Backward compatibility aliases ──

StaffConfigPayload = MemberConfigPayload
CreateStaffRequest = CreateMemberRequest
UpdateStaffRequest = UpdateMemberRequest
PublishStaffRequest = PublishMemberRequest
