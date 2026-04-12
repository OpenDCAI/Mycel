"""Marketplace API router — publish, install, upgrade, check updates."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.web.core.dependencies import get_current_user_id
from backend.web.models.marketplace import (
    CheckUpdatesRequest,
    InstallFromMarketplaceRequest,
    PublishAgentUserToMarketplaceRequest,
    UpgradeFromMarketplaceRequest,
)
from backend.web.services import marketplace_client

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


async def _verify_user_ownership(agent_user_id: str, user_id: str, user_repo: Any) -> None:
    """Raise 403 if *user_id* does not own *agent_user_id*."""

    def _check() -> None:
        user = user_repo.get_by_id(agent_user_id)
        if user is None or user.owner_user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to publish this user",
            )

    await asyncio.to_thread(_check)


@router.post("/publish-agent-user")
async def publish_agent_user_to_marketplace(
    req: PublishAgentUserToMarketplaceRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    request: Request,
) -> dict[str, Any]:
    user_repo = request.app.state.user_repo
    agent_config_repo = getattr(request.app.state, "agent_config_repo", None)
    await _verify_user_ownership(req.user_id, user_id, user_repo)

    from backend.web.services.profile_service import get_profile

    publisher_user = user_repo.get_by_id(user_id)
    profile = await asyncio.to_thread(get_profile, publisher_user)
    username = profile.get("name", "anonymous")

    return await asyncio.to_thread(
        marketplace_client.publish,
        user_id=req.user_id,
        type_=marketplace_client.HUB_AGENT_USER_ITEM_TYPE,
        bump_type=req.bump_type,
        release_notes=req.release_notes,
        tags=req.tags,
        visibility=req.visibility,
        publisher_user_id=user_id,
        publisher_username=username,
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )


@router.post("/download")
async def download_from_marketplace(
    req: InstallFromMarketplaceRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    request: Request,
) -> dict[str, Any]:
    user_repo = request.app.state.user_repo
    agent_config_repo = getattr(request.app.state, "agent_config_repo", None)
    return await asyncio.to_thread(
        marketplace_client.download,
        item_id=req.item_id,
        owner_user_id=user_id,
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )


@router.post("/upgrade")
async def upgrade_from_marketplace(
    req: UpgradeFromMarketplaceRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    request: Request,
) -> dict[str, Any]:
    user_repo = request.app.state.user_repo
    agent_config_repo = getattr(request.app.state, "agent_config_repo", None)
    await _verify_user_ownership(req.user_id, user_id, user_repo)

    return await asyncio.to_thread(
        marketplace_client.upgrade,
        user_id=req.user_id,
        item_id=req.item_id,
        owner_user_id=user_id,
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )


@router.post("/check-updates")
async def check_updates(
    req: CheckUpdatesRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    return await asyncio.to_thread(
        marketplace_client.check_updates,
        items=[item.model_dump() for item in req.items],
    )
