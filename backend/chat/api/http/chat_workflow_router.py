from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.chat.api.http.dependencies import (
    get_accessible_chat_or_404,
    get_chat_repo,
    get_chat_task_service,
    get_chat_workflow_event_service,
    get_chat_workflow_service,
    get_current_user_id,
    get_messaging_service,
)
from storage.errors import StaleChatWorkflowVersionError

router = APIRouter(prefix="/api/chats", tags=["chats"])


class SetChatWorkflowBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    state: str = "active"
    config: dict[str, Any] = Field(default_factory=dict)
    expected_state_version: int | None = Field(default=None, ge=0)


class CreateChatTaskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    description: str
    status: str = "pending"
    active_form: str | None = None
    owner: str | None = None
    blocks: list[str] = Field(default_factory=list)
    blocked_by: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateChatTaskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    subject: str | None = None
    description: str | None = None
    active_form: str | None = None
    owner: str | None = None
    blocks: list[str] | None = None
    blocked_by: list[str] | None = None
    metadata: dict[str, Any] | None = None


class CreateChatWorkflowEventBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    resource_refs: list[dict[str, Any]] = Field(default_factory=list)
    requested_by_user_id: str | None = None
    decision_states: dict[str, dict[str, str]] = Field(default_factory=dict)
    rationales: dict[str, Any] = Field(default_factory=dict)
    final_state: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateChatWorkflowEventBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str | None = None
    decision_states: dict[str, dict[str, str]] | None = None
    rationales: dict[str, Any] | None = None
    final_state: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    settled_at: float | None = None


@router.get("/{chat_id}/workflow")
def get_chat_workflow(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_repo: Annotated[Any, Depends(get_chat_repo)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    chat_workflow_service: Annotated[Any, Depends(get_chat_workflow_service)],
):
    get_accessible_chat_or_404(chat_repo, messaging_service, chat_id, user_id)
    workflow = chat_workflow_service.get_workflow(chat_id)
    if workflow is None:
        raise HTTPException(404, "Chat workflow not found")
    return workflow


@router.put("/{chat_id}/workflow")
def set_chat_workflow(
    chat_id: str,
    body: SetChatWorkflowBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_repo: Annotated[Any, Depends(get_chat_repo)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    chat_workflow_service: Annotated[Any, Depends(get_chat_workflow_service)],
):
    get_accessible_chat_or_404(chat_repo, messaging_service, chat_id, user_id)
    try:
        return chat_workflow_service.set_workflow(
            chat_id,
            kind=body.kind,
            state=body.state,
            config=body.config,
            updated_by_user_id=user_id,
            expected_state_version=body.expected_state_version,
        )
    except StaleChatWorkflowVersionError as exc:
        raise HTTPException(
            409,
            {
                "error": "stale_chat_workflow_state_version",
                "chat_id": exc.chat_id,
                "expected_state_version": exc.expected_state_version,
                "actual_state_version": exc.actual_state_version,
            },
        ) from exc


@router.delete("/{chat_id}/workflow")
def delete_chat_workflow(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_repo: Annotated[Any, Depends(get_chat_repo)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    chat_workflow_service: Annotated[Any, Depends(get_chat_workflow_service)],
):
    get_accessible_chat_or_404(chat_repo, messaging_service, chat_id, user_id)
    chat_workflow_service.delete_workflow(chat_id)
    return {"status": "deleted"}


@router.get("/{chat_id}/workflow/events")
def list_chat_workflow_events(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_repo: Annotated[Any, Depends(get_chat_repo)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    chat_workflow_event_service: Annotated[Any, Depends(get_chat_workflow_event_service)],
):
    get_accessible_chat_or_404(chat_repo, messaging_service, chat_id, user_id)
    return chat_workflow_event_service.list_events(chat_id)


@router.post("/{chat_id}/workflow/events")
def create_chat_workflow_event(
    chat_id: str,
    body: CreateChatWorkflowEventBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_repo: Annotated[Any, Depends(get_chat_repo)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    chat_workflow_event_service: Annotated[Any, Depends(get_chat_workflow_event_service)],
):
    get_accessible_chat_or_404(chat_repo, messaging_service, chat_id, user_id)
    return chat_workflow_event_service.create_event(
        chat_id,
        kind=body.kind,
        resource_refs=body.resource_refs,
        requested_by_user_id=body.requested_by_user_id,
        decision_states=body.decision_states,
        rationales=body.rationales,
        final_state=body.final_state,
        metadata=body.metadata,
    )


@router.get("/{chat_id}/workflow/events/{event_id}")
def get_chat_workflow_event(
    chat_id: str,
    event_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_repo: Annotated[Any, Depends(get_chat_repo)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    chat_workflow_event_service: Annotated[Any, Depends(get_chat_workflow_event_service)],
):
    get_accessible_chat_or_404(chat_repo, messaging_service, chat_id, user_id)
    event = chat_workflow_event_service.get_event(chat_id, event_id)
    if event is None:
        raise HTTPException(404, "Chat workflow event not found")
    return event


@router.patch("/{chat_id}/workflow/events/{event_id}")
def update_chat_workflow_event(
    chat_id: str,
    event_id: str,
    body: UpdateChatWorkflowEventBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_repo: Annotated[Any, Depends(get_chat_repo)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    chat_workflow_event_service: Annotated[Any, Depends(get_chat_workflow_event_service)],
):
    get_accessible_chat_or_404(chat_repo, messaging_service, chat_id, user_id)
    event = chat_workflow_event_service.update_event(
        chat_id,
        event_id,
        state=body.state,
        decision_states=body.decision_states,
        rationales=body.rationales,
        final_state=body.final_state,
        metadata=body.metadata,
        settled_at=body.settled_at,
    )
    if event is None:
        raise HTTPException(404, "Chat workflow event not found")
    return event


@router.delete("/{chat_id}/workflow/events/{event_id}")
def delete_chat_workflow_event(
    chat_id: str,
    event_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_repo: Annotated[Any, Depends(get_chat_repo)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    chat_workflow_event_service: Annotated[Any, Depends(get_chat_workflow_event_service)],
):
    get_accessible_chat_or_404(chat_repo, messaging_service, chat_id, user_id)
    chat_workflow_event_service.delete_event(chat_id, event_id)
    return {"status": "deleted"}


@router.get("/{chat_id}/tasks")
def list_chat_tasks(
    chat_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_repo: Annotated[Any, Depends(get_chat_repo)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    chat_task_service: Annotated[Any, Depends(get_chat_task_service)],
):
    get_accessible_chat_or_404(chat_repo, messaging_service, chat_id, user_id)
    return chat_task_service.list_tasks(chat_id)


@router.post("/{chat_id}/tasks")
def create_chat_task(
    chat_id: str,
    body: CreateChatTaskBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_repo: Annotated[Any, Depends(get_chat_repo)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    chat_task_service: Annotated[Any, Depends(get_chat_task_service)],
):
    get_accessible_chat_or_404(chat_repo, messaging_service, chat_id, user_id)
    return chat_task_service.create_task(
        chat_id,
        subject=body.subject,
        description=body.description,
        status=body.status,
        active_form=body.active_form,
        owner=body.owner,
        blocks=body.blocks,
        blocked_by=body.blocked_by,
        metadata=body.metadata,
    )


@router.get("/{chat_id}/tasks/{task_id}")
def get_chat_task(
    chat_id: str,
    task_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_repo: Annotated[Any, Depends(get_chat_repo)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    chat_task_service: Annotated[Any, Depends(get_chat_task_service)],
):
    get_accessible_chat_or_404(chat_repo, messaging_service, chat_id, user_id)
    task = chat_task_service.get_task(chat_id, task_id)
    if task is None:
        raise HTTPException(404, "Chat task not found")
    return task


@router.patch("/{chat_id}/tasks/{task_id}")
def update_chat_task(
    chat_id: str,
    task_id: str,
    body: UpdateChatTaskBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_repo: Annotated[Any, Depends(get_chat_repo)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    chat_task_service: Annotated[Any, Depends(get_chat_task_service)],
):
    get_accessible_chat_or_404(chat_repo, messaging_service, chat_id, user_id)
    task = chat_task_service.update_task(
        chat_id,
        task_id,
        status=body.status,
        subject=body.subject,
        description=body.description,
        active_form=body.active_form,
        owner=body.owner,
        blocks=body.blocks,
        blocked_by=body.blocked_by,
        metadata=body.metadata,
    )
    if task is None:
        raise HTTPException(404, "Chat task not found")
    return task


@router.delete("/{chat_id}/tasks/{task_id}")
def delete_chat_task(
    chat_id: str,
    task_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    chat_repo: Annotated[Any, Depends(get_chat_repo)],
    messaging_service: Annotated[Any, Depends(get_messaging_service)],
    chat_task_service: Annotated[Any, Depends(get_chat_task_service)],
):
    get_accessible_chat_or_404(chat_repo, messaging_service, chat_id, user_id)
    chat_task_service.delete_task(chat_id, task_id)
    return {"status": "deleted"}
