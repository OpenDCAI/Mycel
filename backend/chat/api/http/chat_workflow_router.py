from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.chat.api.http.dependencies import (
    get_accessible_chat_or_404,
    get_chat_repo,
    get_chat_task_service,
    get_chat_workflow_service,
    get_current_user_id,
    get_messaging_service,
)

router = APIRouter(prefix="/api/chats", tags=["chats"])


class SetChatWorkflowBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    state: str = "active"
    config: dict[str, Any] = Field(default_factory=dict)


class CreateChatTaskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    description: str
    status: str = "pending"
    active_form: str | None = None
    owner: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateChatTaskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    subject: str | None = None
    description: str | None = None
    active_form: str | None = None
    owner: str | None = None
    metadata: dict[str, Any] | None = None


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
    return chat_workflow_service.set_workflow(
        chat_id,
        kind=body.kind,
        state=body.state,
        config=body.config,
        updated_by_user_id=user_id,
    )


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
