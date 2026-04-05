"""Panel API router — Members, Tasks, Library, Profile."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.web.core.dependencies import get_current_user_id
from backend.web.models.panel import (
    BulkDeleteTasksRequest,
    BulkTaskStatusRequest,
    CreateCronJobRequest,
    CreateMemberRequest,
    CreateResourceRequest,
    CreateTaskRequest,
    MemberConfigPayload,
    PublishMemberRequest,
    UpdateCronJobRequest,
    UpdateMemberRequest,
    UpdateProfileRequest,
    UpdateResourceContentRequest,
    UpdateResourceRequest,
    UpdateTaskRequest,
)
from backend.web.services import cron_job_service, library_service, member_service, profile_service, task_service

router = APIRouter(prefix="/api/panel", tags=["panel"])


# ── Members ──


@router.get("/members")
async def list_members(
    user_id: Annotated[str, Depends(get_current_user_id)],
    request: Request,
) -> dict[str, Any]:
    member_repo = getattr(request.app.state, "member_repo", None)
    items = await asyncio.to_thread(member_service.list_members, user_id, member_repo=member_repo)
    return {"items": items}


@router.get("/members/{member_id}")
async def get_member(member_id: str) -> dict[str, Any]:
    item = await asyncio.to_thread(member_service.get_member, member_id)
    if not item:
        raise HTTPException(404, "Member not found")
    return item


@router.post("/members")
async def create_member(
    req: CreateMemberRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    request: Request,
) -> dict[str, Any]:
    member_repo = getattr(request.app.state, "member_repo", None)
    return await asyncio.to_thread(member_service.create_member, req.name, req.description, owner_user_id=user_id, member_repo=member_repo)


@router.put("/members/{member_id}")
async def update_member(member_id: str, req: UpdateMemberRequest, request: Request) -> dict[str, Any]:
    member_repo = getattr(request.app.state, "member_repo", None)
    entity_repo = getattr(request.app.state, "entity_repo", None)
    thread_repo = getattr(request.app.state, "thread_repo", None)
    item = await asyncio.to_thread(
        member_service.update_member,
        member_id,
        member_repo=member_repo,
        entity_repo=entity_repo,
        thread_repo=thread_repo,
        **req.model_dump(),
    )
    if not item:
        raise HTTPException(404, "Member not found")
    return item


@router.put("/members/{member_id}/config")
async def update_member_config(member_id: str, req: MemberConfigPayload) -> dict[str, Any]:
    item = await asyncio.to_thread(member_service.update_member_config, member_id, req.model_dump())
    if not item:
        raise HTTPException(404, "Member not found")
    return item


@router.put("/members/{member_id}/publish")
async def publish_member(member_id: str, req: PublishMemberRequest) -> dict[str, Any]:
    if member_id == "__leon__":
        raise HTTPException(403, "Cannot publish builtin member")
    item = await asyncio.to_thread(member_service.publish_member, member_id, req.bump_type)
    if not item:
        raise HTTPException(404, "Member not found")
    return item


@router.delete("/members/{member_id}")
async def delete_member(member_id: str, request: Request) -> dict[str, Any]:
    if member_id == "__leon__":
        raise HTTPException(403, "Cannot delete builtin member")
    member_repo = getattr(request.app.state, "member_repo", None)
    ok = await asyncio.to_thread(member_service.delete_member, member_id, member_repo=member_repo)
    if not ok:
        raise HTTPException(404, "Member not found")
    return {"success": True}


# ── Tasks ──


@router.get("/tasks")
async def list_tasks() -> dict[str, Any]:
    items = await asyncio.to_thread(task_service.list_tasks)
    return {"items": items}


@router.post("/tasks")
async def create_task(req: CreateTaskRequest) -> dict[str, Any]:
    return await asyncio.to_thread(task_service.create_task, **req.model_dump())


@router.put("/tasks/bulk-status")
async def bulk_update_status(req: BulkTaskStatusRequest) -> dict[str, Any]:
    count = await asyncio.to_thread(task_service.bulk_update_task_status, req.ids, req.status)
    return {"updated": count}


@router.post("/tasks/bulk-delete")
async def bulk_delete_tasks(req: BulkDeleteTasksRequest) -> dict[str, Any]:
    count = await asyncio.to_thread(task_service.bulk_delete_tasks, req.ids)
    return {"deleted": count}


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, req: UpdateTaskRequest) -> dict[str, Any]:
    item = await asyncio.to_thread(task_service.update_task, task_id, **req.model_dump())
    if not item:
        raise HTTPException(404, "Task not found")
    return item


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str) -> dict[str, Any]:
    ok = await asyncio.to_thread(task_service.delete_task, task_id)
    if not ok:
        raise HTTPException(404, "Task not found")
    return {"success": True}


# ── Cron Jobs ──


@router.get("/cron-jobs")
async def list_cron_jobs() -> dict[str, Any]:
    items = await asyncio.to_thread(cron_job_service.list_cron_jobs)
    return {"items": items}


@router.post("/cron-jobs")
async def create_cron_job(req: CreateCronJobRequest) -> dict[str, Any]:
    job = await asyncio.to_thread(
        cron_job_service.create_cron_job,
        name=req.name,
        cron_expression=req.cron_expression,
        description=req.description,
        task_template=req.task_template,
        enabled=int(req.enabled),
    )
    return {"item": job}


@router.put("/cron-jobs/{job_id}")
async def update_cron_job(job_id: str, req: UpdateCronJobRequest) -> dict[str, Any]:
    fields = req.model_dump(exclude_none=True)
    if "enabled" in fields:
        fields["enabled"] = int(fields["enabled"])
    job = await asyncio.to_thread(cron_job_service.update_cron_job, job_id, **fields)
    if not job:
        raise HTTPException(404, "Cron job not found")
    return {"item": job}


@router.delete("/cron-jobs/{job_id}")
async def delete_cron_job(job_id: str) -> dict[str, Any]:
    ok = await asyncio.to_thread(cron_job_service.delete_cron_job, job_id)
    if not ok:
        raise HTTPException(404, "Cron job not found")
    return {"ok": True}


@router.post("/cron-jobs/{job_id}/run")
async def trigger_cron_job(job_id: str, request: Request) -> dict[str, Any]:
    cron_service = getattr(request.app.state, "cron_service", None)
    if not cron_service:
        raise HTTPException(503, "Cron service not available")
    task = await cron_service.trigger_job(job_id)
    if not task:
        raise HTTPException(404, "Cron job not found or disabled")
    return {"item": task}


# ── Library ──


@router.get("/library/{resource_type}")
async def list_library(
    resource_type: str,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    items = await asyncio.to_thread(library_service.list_library, resource_type, user_id, request.app.state.recipe_repo)
    return {"items": items}


@router.post("/library/{resource_type}")
async def create_resource(
    resource_type: str,
    req: CreateResourceRequest,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    category = req.provider_type or ""
    return await asyncio.to_thread(
        library_service.create_resource,
        resource_type,
        req.name,
        req.desc,
        category,
        req.features,
        user_id,
        request.app.state.recipe_repo,
    )


@router.put("/library/{resource_type}/{resource_id}")
async def update_resource(
    resource_type: str,
    resource_id: str,
    req: UpdateResourceRequest,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    item = await asyncio.to_thread(
        library_service.update_resource,
        resource_type,
        resource_id,
        user_id,
        request.app.state.recipe_repo,
        **req.model_dump(),
    )
    if not item:
        raise HTTPException(404, "Resource not found")
    return item


@router.delete("/library/{resource_type}/{resource_id}")
async def delete_resource(
    resource_type: str,
    resource_id: str,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    ok = await asyncio.to_thread(library_service.delete_resource, resource_type, resource_id, user_id, request.app.state.recipe_repo)
    if not ok:
        raise HTTPException(404, "Resource not found")
    return {"success": True}


@router.get("/library/{resource_type}/names")
async def list_library_names(
    resource_type: str,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    items = await asyncio.to_thread(library_service.list_library_names, resource_type, user_id, request.app.state.recipe_repo)
    return {"items": items}


@router.get("/library/{resource_type}/{resource_name}/used-by")
async def get_used_by(resource_type: str, resource_name: str) -> dict[str, Any]:
    members = await asyncio.to_thread(library_service.get_resource_used_by, resource_type, resource_name)
    return {"count": len(members), "members": members}


@router.get("/library/{resource_type}/{resource_id}/content")
async def get_resource_content(
    resource_type: str,
    resource_id: str,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    content = await asyncio.to_thread(
        library_service.get_resource_content,
        resource_type,
        resource_id,
        user_id,
        request.app.state.recipe_repo,
    )
    if content is None:
        raise HTTPException(404, "Resource not found")
    return {"content": content}


@router.put("/library/{resource_type}/{resource_id}/content")
async def update_resource_content(resource_type: str, resource_id: str, req: UpdateResourceContentRequest) -> dict[str, Any]:
    if resource_type == "recipe":
        raise HTTPException(400, "Recipes are read-only")
    ok = await asyncio.to_thread(library_service.update_resource_content, resource_type, resource_id, req.content)
    if not ok:
        raise HTTPException(404, "Resource not found or invalid content")
    return {"success": True}


# ── Profile ──


@router.get("/profile")
async def get_profile(
    user_id: Annotated[str, Depends(get_current_user_id)],
    request: Request,
) -> dict[str, Any]:
    member = request.app.state.member_repo.get_by_id(user_id)
    return await asyncio.to_thread(profile_service.get_profile, member)


@router.put("/profile")
async def update_profile(req: UpdateProfileRequest) -> dict[str, Any]:
    return await asyncio.to_thread(profile_service.update_profile, **req.model_dump())
