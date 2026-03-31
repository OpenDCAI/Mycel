"""Marketplace API router — publish, install, upgrade, check updates."""
import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from backend.web.core.dependencies import get_current_user_id
from backend.web.models.marketplace import (
    CheckUpdatesRequest,
    InstallFromMarketplaceRequest,
    PublishToMarketplaceRequest,
    UpgradeFromMarketplaceRequest,
)
from backend.web.services import marketplace_client

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


async def _verify_member_ownership(member_id: str, user_id: str) -> None:
    """Raise 403 if *user_id* does not own *member_id* in the SQLite registry."""
    from storage.providers.sqlite.member_repo import SQLiteMemberRepo

    def _check() -> None:
        repo = SQLiteMemberRepo()
        try:
            member = repo.get_by_id(member_id)
            if member is None or member.owner_user_id != user_id:
                raise HTTPException(
                    status_code=403,
                    detail="Not authorized to publish this member",
                )
        finally:
            repo.close()

    await asyncio.to_thread(_check)


@router.post("/publish")
async def publish_to_marketplace(
    req: PublishToMarketplaceRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    await _verify_member_ownership(req.member_id, user_id)

    from backend.web.services.profile_service import get_profile
    profile = await asyncio.to_thread(get_profile)
    username = profile.get("name", "anonymous")

    result = await asyncio.to_thread(
        marketplace_client.publish,
        member_id=req.member_id,
        type_=req.type,
        bump_type=req.bump_type,
        release_notes=req.release_notes,
        tags=req.tags,
        visibility=req.visibility,
        publisher_user_id=user_id,
        publisher_username=username,
    )
    return result


@router.post("/download")
async def download_from_marketplace(
    req: InstallFromMarketplaceRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    result = await asyncio.to_thread(
        marketplace_client.download,
        item_id=req.item_id,
    )
    return result


@router.post("/upgrade")
async def upgrade_from_marketplace(
    req: UpgradeFromMarketplaceRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    await _verify_member_ownership(req.member_id, user_id)

    result = await asyncio.to_thread(
        marketplace_client.upgrade,
        member_id=req.member_id,
        item_id=req.item_id,
        owner_user_id=user_id,
    )
    return result


@router.post("/check-updates")
async def check_updates(
    req: CheckUpdatesRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    result = await asyncio.to_thread(
        marketplace_client.check_updates,
        items=[item.model_dump() for item in req.items],
    )
    return result
