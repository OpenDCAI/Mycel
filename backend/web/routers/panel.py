"""Panel API router — Agents, Library, Profile."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.web.core.dependencies import get_current_user_id
from backend.web.models.panel import (
    AgentConfigPayload,
    CreateAgentRequest,
    CreateResourceRequest,
    PublishAgentRequest,
    UpdateAgentRequest,
    UpdateProfileRequest,
    UpdateResourceContentRequest,
    UpdateResourceRequest,
)
from backend.web.services import library_service, member_service, profile_service

router = APIRouter(prefix="/api/panel", tags=["panel"])
CurrentUserId = Annotated[str, Depends(get_current_user_id)]


def _require_owned_agent_user(agent_id: str, user_id: str, user_repo: Any) -> Any:
    user = user_repo.get_by_id(agent_id)
    if user is None or user.type.value != "agent":
        raise HTTPException(404, "Agent not found")
    if user.owner_user_id != user_id:
        raise HTTPException(403, "Forbidden")
    return user


def _get_owned_agent_or_404_with_config(agent_id: str, user_id: str, user_repo: Any, agent_config_repo: Any) -> dict[str, Any]:
    _require_owned_agent_user(agent_id, user_id, user_repo)
    item = member_service.get_member(agent_id, user_repo=user_repo, agent_config_repo=agent_config_repo)
    if not item:
        raise HTTPException(404, "Agent not found")
    return item


def _ensure_agent_has_no_threads_or_409(agent_id: str, thread_repo: Any) -> None:
    rows = thread_repo.list_by_agent_user(agent_id)
    if rows:
        raise HTTPException(409, "Cannot delete agent with existing threads")


# ── Agents ──


@router.get("/agents")
async def list_members(
    user_id: CurrentUserId,
    request: Request,
) -> dict[str, Any]:
    user_repo = request.app.state.user_repo
    agent_config_repo = getattr(request.app.state, "agent_config_repo", None)
    items = await asyncio.to_thread(member_service.list_members, user_id, user_repo=user_repo, agent_config_repo=agent_config_repo)
    return {"items": items}


@router.get("/agents/{agent_id}")
async def get_member(
    agent_id: str,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _get_owned_agent_or_404_with_config,
        agent_id,
        user_id,
        request.app.state.user_repo,
        getattr(request.app.state, "agent_config_repo", None),
    )


@router.post("/agents")
async def create_member(
    req: CreateAgentRequest,
    user_id: CurrentUserId,
    request: Request,
) -> dict[str, Any]:
    user_repo = request.app.state.user_repo
    agent_config_repo = getattr(request.app.state, "agent_config_repo", None)
    return await asyncio.to_thread(
        member_service.create_member,
        req.name,
        req.description,
        owner_user_id=user_id,
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )


@router.put("/agents/{agent_id}")
async def update_member(
    agent_id: str,
    req: UpdateAgentRequest,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    user_repo = request.app.state.user_repo
    agent_config_repo = getattr(request.app.state, "agent_config_repo", None)
    await asyncio.to_thread(_require_owned_agent_user, agent_id, user_id, user_repo)
    item = await asyncio.to_thread(
        member_service.update_member,
        agent_id,
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
        **req.model_dump(),
    )
    if not item:
        raise HTTPException(404, "Agent not found")
    return item


@router.put("/agents/{agent_id}/config")
async def update_member_config(
    agent_id: str,
    req: AgentConfigPayload,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    user_repo = request.app.state.user_repo
    await asyncio.to_thread(_require_owned_agent_user, agent_id, user_id, user_repo)
    agent_config_repo = getattr(request.app.state, "agent_config_repo", None)
    item = await asyncio.to_thread(
        member_service.update_member_config,
        agent_id,
        req.model_dump(),
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )
    if not item:
        raise HTTPException(404, "Agent not found")
    return item


@router.put("/agents/{agent_id}/publish")
async def publish_member(
    agent_id: str,
    req: PublishAgentRequest,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    if agent_id == "__leon__":
        raise HTTPException(403, "Cannot publish builtin agent")
    user_repo = request.app.state.user_repo
    await asyncio.to_thread(_require_owned_agent_user, agent_id, user_id, user_repo)
    agent_config_repo = getattr(request.app.state, "agent_config_repo", None)
    item = await asyncio.to_thread(
        member_service.publish_member,
        agent_id,
        req.bump_type,
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )
    if not item:
        raise HTTPException(404, "Agent not found")
    return item


@router.delete("/agents/{agent_id}")
async def delete_member(
    agent_id: str,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    if agent_id == "__leon__":
        raise HTTPException(403, "Cannot delete builtin agent")
    user_repo = request.app.state.user_repo
    await asyncio.to_thread(_require_owned_agent_user, agent_id, user_id, user_repo)
    thread_repo = getattr(request.app.state, "thread_repo", None)
    if thread_repo is not None:
        await asyncio.to_thread(_ensure_agent_has_no_threads_or_409, agent_id, thread_repo)
    agent_config_repo = getattr(request.app.state, "agent_config_repo", None)
    thread_launch_pref_repo = getattr(request.app.state, "thread_launch_pref_repo", None)
    ok = await asyncio.to_thread(
        member_service.delete_member,
        agent_id,
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
        thread_launch_pref_repo=thread_launch_pref_repo,
    )
    if not ok:
        raise HTTPException(404, "Agent not found")
    return {"success": True}


# ── Library ──


@router.get("/library/{resource_type}")
async def list_library(
    resource_type: str,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    items = await asyncio.to_thread(library_service.list_library, resource_type, user_id, request.app.state.recipe_repo)
    return {"items": items}


@router.post("/library/{resource_type}")
async def create_resource(
    resource_type: str,
    req: CreateResourceRequest,
    request: Request,
    user_id: CurrentUserId,
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
    user_id: CurrentUserId,
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
    user_id: CurrentUserId,
) -> dict[str, Any]:
    ok = await asyncio.to_thread(library_service.delete_resource, resource_type, resource_id, user_id, request.app.state.recipe_repo)
    if not ok:
        raise HTTPException(404, "Resource not found")
    return {"success": True}


@router.get("/library/{resource_type}/names")
async def list_library_names(
    resource_type: str,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    items = await asyncio.to_thread(library_service.list_library_names, resource_type, user_id, request.app.state.recipe_repo)
    return {"items": items}


@router.get("/library/{resource_type}/{resource_name}/used-by")
async def get_used_by(
    resource_type: str,
    resource_name: str,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    users = await asyncio.to_thread(
        library_service.get_resource_used_by,
        resource_type,
        resource_name,
        user_id,
        user_repo=request.app.state.user_repo,
        agent_config_repo=getattr(request.app.state, "agent_config_repo", None),
    )
    return {"count": len(users), "users": users}


@router.get("/library/{resource_type}/{resource_id}/content")
async def get_resource_content(
    resource_type: str,
    resource_id: str,
    request: Request,
    user_id: CurrentUserId,
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
    user_id: CurrentUserId,
    request: Request,
) -> dict[str, Any]:
    user = request.app.state.user_repo.get_by_id(user_id)
    return await asyncio.to_thread(profile_service.get_profile, user)


@router.put("/profile")
async def update_profile(
    req: UpdateProfileRequest,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        profile_service.update_profile,
        user_repo=request.app.state.user_repo,
        user_id=user_id,
        **req.model_dump(),
    )
