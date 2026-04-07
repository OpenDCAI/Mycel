"""User-backed identity endpoints for discovery, avatars, and agent thread lookup."""

import io
import logging
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.web.core.dependencies import get_app, get_current_user_id
from backend.web.core.paths import avatars_dir
from backend.web.utils.serializers import avatar_url
from storage.contracts import UserType

logger = logging.getLogger(__name__)

AVATARS_DIR = avatars_dir()
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
AVATAR_SIZE = 256
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


def process_and_save_avatar(source: Path | bytes, user_id: str) -> str:
    """Process image through PIL pipeline and save as 256x256 PNG.

    Args:
        source: Path to image file or raw bytes
        user_id: used for filename

    Returns:
        Relative avatar path (e.g. "avatars/{user_id}.png")
    """
    from PIL import Image, ImageOps

    if isinstance(source, (bytes, bytearray)):
        img = Image.open(io.BytesIO(source))
    else:
        img = Image.open(source)
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    img = ImageOps.fit(img, (AVATAR_SIZE, AVATAR_SIZE), method=Image.Resampling.LANCZOS)
    AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    img.save(AVATARS_DIR / f"{user_id}.png", format="PNG", optimize=True)
    return f"avatars/{user_id}.png"


router = APIRouter(prefix="/api/entities", tags=["entities"])

# ---------------------------------------------------------------------------
# Members (legacy route prefix, user-backed agent directory)
# ---------------------------------------------------------------------------

members_router = APIRouter(prefix="/api/members", tags=["members"])


@members_router.get("")
async def list_members(
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """List all agent users for the member directory page."""
    user_repo = app.state.user_repo

    all_users = user_repo.list_all()
    result = []
    for user in all_users:
        if user.type is not UserType.AGENT:
            continue
        owner = user_repo.get_by_id(user.owner_user_id) if user.owner_user_id else None
        result.append(
            {
                "id": user.id,
                "name": user.display_name,
                "type": user.type.value,
                "avatar_url": avatar_url(user.id, bool(user.avatar)),
                "description": None,
                "owner_name": owner.display_name if owner else None,
                "is_mine": user.owner_user_id == user_id,
                "created_at": user.created_at,
            }
        )
    return result


def _avatar_path(user_id: str) -> Path:
    safe_id = Path(user_id).name
    return AVATARS_DIR / f"{safe_id}.png"


def _get_owned_avatar_user_or_404(user_id: str, current_user_id: str, user_repo: Any) -> Any:
    user = user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user_id == current_user_id or user.owner_user_id == current_user_id:
        return user
    raise HTTPException(403, "Not authorized")


@members_router.put("/{user_id}/avatar")
async def upload_avatar(
    user_id: str,
    file: UploadFile,
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict[str, str]:
    """Upload/replace avatar image. Resizes to 256x256 PNG."""
    repo = app.state.user_repo
    _get_owned_avatar_user_or_404(user_id, current_user_id, repo)
    ct = file.content_type or ""
    if ct not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(400, f"Unsupported image type: {ct}")
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(400, "Empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"File too large (max {MAX_UPLOAD_BYTES // 1024 // 1024}MB)")
    try:
        avatar_path = process_and_save_avatar(data, user_id)
    except Exception as e:
        logger.error(f"Avatar processing failed for {user_id}: {e}")
        raise HTTPException(400, f"Invalid image: {e}")
    repo.update(user_id, avatar=avatar_path, updated_at=time.time())
    return {"status": "ok", "avatar": f"avatars/{user_id}.png"}


@members_router.get("/{user_id}/avatar")
async def get_avatar(user_id: str) -> FileResponse:
    """Serve avatar image. No auth (public). 300s browser cache."""
    path = _avatar_path(user_id)
    if not path.exists():
        raise HTTPException(404, "No avatar")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=300"})


@members_router.delete("/{user_id}/avatar")
async def delete_avatar(
    user_id: str,
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict[str, str]:
    """Delete avatar."""
    repo = app.state.user_repo
    _get_owned_avatar_user_or_404(user_id, current_user_id, repo)
    path = _avatar_path(user_id)
    if path.exists():
        path.unlink()
    repo.update(user_id, avatar=None, updated_at=time.time())
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Entities (social identities for chat discovery)
# ---------------------------------------------------------------------------


@router.get("")
async def list_entities(
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """List chattable users for discovery (New Chat picker). Excludes the current user."""
    user_repo = app.state.user_repo
    users = user_repo.list_all()
    user_map = {user.id: user for user in users}

    items = []

    for user in users:
        if user.id == user_id:
            continue
        if user.type is UserType.HUMAN:
            items.append(
                {
                    "user_id": user.id,
                    "name": user.display_name,
                    "type": "human",
                    "avatar_url": avatar_url(user.id, bool(user.avatar)),
                    "owner_name": None,
                    "agent_name": user.display_name,
                    "default_thread_id": None,
                    "is_default_thread": None,
                    "branch_index": None,
                }
            )
        else:
            owner = user_map.get(user.owner_user_id) if user.owner_user_id else None
            default_thread = app.state.thread_repo.get_default_thread(user.id)
            items.append(
                {
                    "user_id": user.id,
                    "name": user.display_name,
                    "type": user.type.value,
                    "avatar_url": avatar_url(user.id, bool(user.avatar)),
                    "owner_name": owner.display_name if owner else None,
                    "agent_name": user.display_name,
                    "default_thread_id": default_thread["id"] if default_thread else None,
                    "is_default_thread": default_thread["is_main"] if default_thread else None,
                    "branch_index": default_thread["branch_index"] if default_thread else None,
                }
            )
    return items


@router.get("/{user_id}/profile")
async def get_entity_profile(
    user_id: str,
    app: Annotated[Any, Depends(get_app)],
):
    """Public agent profile. No auth required (frontend uses plain fetch)."""
    user = _get_user_or_404(app, user_id)
    if user.type is not UserType.AGENT:
        raise HTTPException(404, "Profile not available for this user type")
    return {
        "id": user.id,
        "name": user.display_name,
        "type": user.type.value,
        "avatar_url": avatar_url(user.id, bool(user.avatar)),
        "description": None,
    }


@router.get("/{user_id}/agent-thread")
async def get_agent_thread(
    user_id: str,
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Get the default representative thread for an agent user."""
    user = _get_user_or_404(app, user_id)
    default_thread = app.state.thread_repo.get_default_thread(user_id)
    if user.type is UserType.AGENT and default_thread is not None:
        return {"user_id": user_id, "default_thread_id": default_thread["id"]}
    raise HTTPException(404, "No agent thread found")


def _get_user_or_404(app: Any, user_id: str) -> Any:
    user = app.state.user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user
