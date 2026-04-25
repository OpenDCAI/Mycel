import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.chat.api.http.dependencies import get_contact_repo, get_thread_repo
from backend.identity import profile as profile_owner
from backend.library import service as library_service
from backend.threads import agent_user_service
from backend.web.core.dependencies import get_current_user, get_current_user_id
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

router = APIRouter(prefix="/api/panel", tags=["panel"])
CurrentUserId = Annotated[str, Depends(get_current_user_id)]
CurrentUser = Annotated[Any, Depends(get_current_user)]


def _require_owned_agent_user(agent_id: str, user_id: str, user_repo: Any) -> Any:
    user = user_repo.get_by_id(agent_id)
    if user is None or user.type.value != "agent":
        raise HTTPException(404, "Agent not found")
    if user.owner_user_id != user_id:
        raise HTTPException(403, "Forbidden")
    return user


def _get_owned_agent_or_404_with_config(agent_id: str, user_id: str, user_repo: Any, agent_config_repo: Any) -> dict[str, Any]:
    _require_owned_agent_user(agent_id, user_id, user_repo)
    item = agent_user_service.get_agent_user(agent_id, user_repo=user_repo, agent_config_repo=agent_config_repo)
    if not item:
        raise HTTPException(404, "Agent not found")
    return item


def _ensure_agent_has_no_threads_or_409(agent_id: str, thread_repo: Any) -> None:
    rows = thread_repo.list_by_agent_user(agent_id)
    if rows:
        raise HTTPException(409, "Cannot delete agent with existing threads")


def _agent_config_repo(request: Request) -> Any | None:
    runtime_storage = getattr(request.app.state, "runtime_storage_state", None)
    storage_container = getattr(runtime_storage, "storage_container", None)
    repo_factory = getattr(storage_container, "agent_config_repo", None)
    return repo_factory() if callable(repo_factory) else None


def _recipe_repo(request: Request) -> Any:
    runtime_storage = getattr(request.app.state, "runtime_storage_state", None)
    recipe_repo = getattr(runtime_storage, "recipe_repo", None)
    if recipe_repo is None:
        raise RuntimeError("recipe_repo is required for panel library routes")
    return recipe_repo


def _recipe_repo_for(resource_type: str, request: Request) -> Any | None:
    if resource_type != "sandbox-template":
        return None
    return _recipe_repo(request)


def _skill_repo(request: Request) -> Any:
    runtime_storage = getattr(request.app.state, "runtime_storage_state", None)
    storage_container = getattr(runtime_storage, "storage_container", None)
    repo_factory = getattr(storage_container, "skill_repo", None)
    repo = repo_factory() if callable(repo_factory) else None
    if repo is None:
        raise RuntimeError("skill_repo is required for panel library routes")
    return repo


def _skill_repo_for(resource_type: str, request: Request) -> Any | None:
    if resource_type != "skill":
        return None
    return _skill_repo(request)


def _panel_contact_repo(request: Request) -> Any:
    try:
        return get_contact_repo(request.app)
    except HTTPException as exc:
        raise HTTPException(503, "chat bootstrap not attached: contact_repo") from exc


# ── Agents ──


@router.get("/agents")
async def list_agents(
    user_id: CurrentUserId,
    request: Request,
) -> dict[str, Any]:
    user_repo = request.app.state.user_repo
    agent_config_repo = _agent_config_repo(request)
    items = await asyncio.to_thread(
        agent_user_service.list_agent_user_summaries,
        user_id,
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )
    return {"items": items}


@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _get_owned_agent_or_404_with_config,
        agent_id,
        user_id,
        request.app.state.user_repo,
        _agent_config_repo(request),
    )


@router.post("/agents")
async def create_agent(
    req: CreateAgentRequest,
    user_id: CurrentUserId,
    request: Request,
) -> dict[str, Any]:
    user_repo = request.app.state.user_repo
    agent_config_repo = _agent_config_repo(request)
    # @@@panel-chat-consumer - panel owns the agent CRUD route, but contact
    # edge cleanup is chat-owned truth. Borrow the repo explicitly from the
    # shared chat HTTP dependency surface so panel does not keep its own
    # parallel chat-runtime accessor layer alive.
    contact_repo = _panel_contact_repo(request)
    return await asyncio.to_thread(
        agent_user_service.create_agent_user,
        req.name,
        req.description,
        owner_user_id=user_id,
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
        contact_repo=contact_repo,
    )


@router.put("/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    req: UpdateAgentRequest,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    user_repo = request.app.state.user_repo
    agent_config_repo = _agent_config_repo(request)
    await asyncio.to_thread(_require_owned_agent_user, agent_id, user_id, user_repo)
    item = await asyncio.to_thread(
        agent_user_service.update_agent_user,
        agent_id,
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
        name=req.name,
        description=req.description,
        status=req.status,
    )
    if not item:
        raise HTTPException(404, "Agent not found")
    return item


@router.put("/agents/{agent_id}/config")
async def update_agent_config(
    agent_id: str,
    req: AgentConfigPayload,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    user_repo = request.app.state.user_repo
    await asyncio.to_thread(_require_owned_agent_user, agent_id, user_id, user_repo)
    agent_config_repo = _agent_config_repo(request)
    item = await asyncio.to_thread(
        agent_user_service.update_agent_user_config,
        agent_id,
        req.model_dump(exclude_unset=True),
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
        skill_repo=_skill_repo(request),
    )
    if not item:
        raise HTTPException(404, "Agent not found")
    return item


@router.put("/agents/{agent_id}/publish")
async def publish_agent(
    agent_id: str,
    req: PublishAgentRequest,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    if agent_id == "__leon__":
        raise HTTPException(403, "Cannot publish builtin agent")
    user_repo = request.app.state.user_repo
    await asyncio.to_thread(_require_owned_agent_user, agent_id, user_id, user_repo)
    agent_config_repo = _agent_config_repo(request)
    item = await asyncio.to_thread(
        agent_user_service.publish_agent_user,
        agent_id,
        req.bump_type,
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )
    if not item:
        raise HTTPException(404, "Agent not found")
    return item


@router.delete("/agents/{agent_id}")
async def delete_agent(
    agent_id: str,
    request: Request,
    user_id: CurrentUserId,
    thread_repo: Annotated[Any, Depends(get_thread_repo)],
) -> dict[str, Any]:
    if agent_id == "__leon__":
        raise HTTPException(403, "Cannot delete builtin agent")
    user_repo = request.app.state.user_repo
    await asyncio.to_thread(_require_owned_agent_user, agent_id, user_id, user_repo)
    if thread_repo is None:
        raise HTTPException(503, "Thread repo unavailable")
    await asyncio.to_thread(_ensure_agent_has_no_threads_or_409, agent_id, thread_repo)
    agent_config_repo = _agent_config_repo(request)
    contact_repo = _panel_contact_repo(request)
    ok = await asyncio.to_thread(
        agent_user_service.delete_agent_user,
        agent_id,
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
        contact_repo=contact_repo,
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
    try:
        items = await asyncio.to_thread(
            library_service.list_library,
            resource_type,
            user_id,
            _recipe_repo_for(resource_type, request),
            _skill_repo_for(resource_type, request),
        )
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return {"items": items}


@router.post("/library/{resource_type}")
async def create_resource(
    resource_type: str,
    req: CreateResourceRequest,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    category = req.provider_type or ""
    try:
        return await asyncio.to_thread(
            library_service.create_resource,
            resource_type,
            req.name,
            req.desc,
            category,
            req.features,
            req.provider_name,
            user_id,
            _recipe_repo_for(resource_type, request),
            _skill_repo_for(resource_type, request),
            content=req.content,
        )
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.put("/library/{resource_type}/{resource_id}")
async def update_resource(
    resource_type: str,
    resource_id: str,
    req: UpdateResourceRequest,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    try:
        item = await asyncio.to_thread(
            library_service.update_resource,
            resource_type,
            resource_id,
            user_id,
            _recipe_repo_for(resource_type, request),
            _skill_repo_for(resource_type, request),
            name=req.name,
            desc=req.desc,
            features=req.features,
        )
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
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
    recipe_repo = _recipe_repo_for(resource_type, request)
    skill_repo = _skill_repo_for(resource_type, request)
    if resource_type == "skill":
        if skill_repo is None:
            raise HTTPException(500, "skill_repo is required for panel library routes")
        skill = await asyncio.to_thread(skill_repo.get_by_id, user_id, resource_id)
        if skill is not None:
            used_by = await asyncio.to_thread(
                library_service.get_resource_used_by,
                "skill",
                skill.name,
                user_id,
                user_repo=request.app.state.user_repo,
                agent_config_repo=_agent_config_repo(request),
            )
            if used_by:
                raise HTTPException(409, f"Skill is still assigned to Agent: {', '.join(used_by)}")
    try:
        ok = await asyncio.to_thread(
            library_service.delete_resource,
            resource_type,
            resource_id,
            user_id,
            recipe_repo,
            skill_repo,
        )
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    if not ok:
        raise HTTPException(404, "Resource not found")
    return {"success": True}


@router.get("/library/{resource_type}/names")
async def list_library_names(
    resource_type: str,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    try:
        items = await asyncio.to_thread(
            library_service.list_library_names,
            resource_type,
            user_id,
            _recipe_repo_for(resource_type, request),
            _skill_repo_for(resource_type, request),
        )
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return {"items": items}


@router.get("/library/{resource_type}/{resource_name}/used-by")
async def get_used_by(
    resource_type: str,
    resource_name: str,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    try:
        users = await asyncio.to_thread(
            library_service.get_resource_used_by,
            resource_type,
            resource_name,
            user_id,
            user_repo=request.app.state.user_repo,
            agent_config_repo=_agent_config_repo(request),
        )
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return {"count": len(users), "users": users}


@router.get("/library/{resource_type}/{resource_id}/content")
async def get_resource_content(
    resource_type: str,
    resource_id: str,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    try:
        content = await asyncio.to_thread(
            library_service.get_resource_content,
            resource_type,
            resource_id,
            user_id,
            _recipe_repo_for(resource_type, request),
            _skill_repo_for(resource_type, request),
        )
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    if content is None:
        raise HTTPException(404, "Resource not found")
    return {"content": content}


@router.put("/library/{resource_type}/{resource_id}/content")
async def update_resource_content(
    resource_type: str,
    resource_id: str,
    req: UpdateResourceContentRequest,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    if resource_type == "sandbox-template":
        raise HTTPException(400, "Sandbox templates are read-only")
    try:
        ok = await asyncio.to_thread(
            library_service.update_resource_content,
            resource_type,
            resource_id,
            req.content,
            user_id,
            _skill_repo_for(resource_type, request),
        )
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    if not ok:
        raise HTTPException(404, "Resource not found or invalid content")
    return {"success": True}


# ── Profile ──


@router.get("/profile")
async def get_profile(
    user: CurrentUser,
) -> dict[str, Any]:
    return profile_owner.get_profile(user)


@router.put("/profile")
async def update_profile(
    req: UpdateProfileRequest,
    request: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        profile_owner.update_profile,
        user_repo=request.app.state.user_repo,
        user_id=user_id,
        name=req.name,
        email=req.email,
    )
