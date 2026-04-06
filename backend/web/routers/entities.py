"""Entity & Member endpoints — new entity-chat system."""

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
from storage.contracts import MemberType

logger = logging.getLogger(__name__)

AVATARS_DIR = avatars_dir()
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
AVATAR_SIZE = 256
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


def process_and_save_avatar(source: Path | bytes, member_id: str) -> str:
    """Process image through PIL pipeline and save as 256x256 PNG.

    Args:
        source: Path to image file or raw bytes
        member_id: used for filename

    Returns:
        Relative avatar path (e.g. "avatars/{member_id}.png")
    """
    from PIL import Image, ImageOps

    if isinstance(source, (bytes, bytearray)):
        img = Image.open(io.BytesIO(source))
    else:
        img = Image.open(source)
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    img = ImageOps.fit(img, (AVATAR_SIZE, AVATAR_SIZE), method=Image.LANCZOS)
    AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    img.save(AVATARS_DIR / f"{member_id}.png", format="PNG", optimize=True)
    return f"avatars/{member_id}.png"


router = APIRouter(prefix="/api/entities", tags=["entities"])

# ---------------------------------------------------------------------------
# Members (agent directory)
# ---------------------------------------------------------------------------

members_router = APIRouter(prefix="/api/members", tags=["members"])


@members_router.get("")
async def list_members(
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """List all agent members (templates). For member directory page."""
    member_repo = app.state.member_repo

    all_members = member_repo.list_all()
    result = []
    for m in all_members:
        if m.type != "mycel_agent":
            continue
        owner = member_repo.get_by_id(m.owner_user_id) if m.owner_user_id else None
        result.append(
            {
                "id": m.id,
                "name": m.name,
                "type": m.type,
                "avatar_url": avatar_url(m.id, bool(m.avatar)),
                "description": m.description,
                "owner_name": owner.name if owner else None,
                "is_mine": m.owner_user_id == user_id,
                "created_at": m.created_at,
            }
        )
    return result


def _avatar_path(member_id: str) -> Path:
    safe_id = Path(member_id).name
    return AVATARS_DIR / f"{safe_id}.png"


@members_router.put("/{member_id}/avatar")
async def upload_avatar(
    member_id: str,
    file: UploadFile,
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict[str, str]:
    """Upload/replace avatar image. Resizes to 256x256 PNG."""
    repo = app.state.member_repo
    member = repo.get_by_id(member_id)
    if not member:
        raise HTTPException(404, "Member not found")
    if member_id != current_user_id and member.owner_user_id != current_user_id:
        raise HTTPException(403, "Not authorized")
    ct = file.content_type or ""
    if ct not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(400, f"Unsupported image type: {ct}")
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(400, "Empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"File too large (max {MAX_UPLOAD_BYTES // 1024 // 1024}MB)")
    try:
        avatar_path = process_and_save_avatar(data, member_id)
    except Exception as e:
        logger.error(f"Avatar processing failed for {member_id}: {e}")
        raise HTTPException(400, f"Invalid image: {e}")
    repo.update(member_id, avatar=avatar_path, updated_at=time.time())
    return {"status": "ok", "avatar": f"avatars/{member_id}.png"}


@members_router.get("/{member_id}/avatar")
async def get_avatar(member_id: str) -> FileResponse:
    """Serve avatar image. No auth (public). 300s browser cache."""
    path = _avatar_path(member_id)
    if not path.exists():
        raise HTTPException(404, "No avatar")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=300"})


@members_router.delete("/{member_id}/avatar")
async def delete_avatar(
    member_id: str,
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict[str, str]:
    """Delete avatar."""
    repo = app.state.member_repo
    member = repo.get_by_id(member_id)
    if not member:
        raise HTTPException(404, "Member not found")
    if member_id != current_user_id and member.owner_user_id != current_user_id:
        raise HTTPException(403, "Not authorized")
    path = _avatar_path(member_id)
    if path.exists():
        path.unlink()
    repo.update(member_id, avatar=None, updated_at=time.time())
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Entities (social identities for chat discovery)
# ---------------------------------------------------------------------------


@router.get("")
async def list_entities(
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """List chattable entities for discovery (New Chat picker).
    Humans are represented by their user_id; agents by their member_id.
    Excludes the current user (you don't chat with yourself)."""
    member_repo = app.state.member_repo
    members = member_repo.list_all()
    member_map = {m.id: m for m in members}

    items = []

    for m in members:
        if m.id == user_id:
            continue
        if m.type == MemberType.HUMAN:
            items.append(
                {
                    "id": m.id,
                    "name": m.name,
                    "type": "human",
                    "avatar_url": avatar_url(m.id, bool(m.avatar)),
                    "owner_name": None,
                    "member_name": m.name,
                    "thread_id": None,
                    "is_main": None,
                    "branch_index": None,
                }
            )
        else:
            owner = member_map.get(m.owner_user_id) if m.owner_user_id else None
            thread = app.state.thread_repo.get_by_id(m.main_thread_id) if m.main_thread_id else None
            items.append(
                {
                    "id": m.id,
                    "name": m.name,
                    "type": m.type.value if hasattr(m.type, "value") else str(m.type),
                    "avatar_url": avatar_url(m.id, bool(m.avatar)),
                    "owner_name": owner.name if owner else None,
                    "member_name": m.name,
                    "thread_id": m.main_thread_id,
                    "is_main": thread["is_main"] if thread else None,
                    "branch_index": thread["branch_index"] if thread else None,
                }
            )
    return items


@router.get("/{user_id}/agent-thread")
async def get_agent_thread(
    user_id: str,
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Get the thread_id for an agent's main thread. user_id here is the agent's member_id."""
    member = app.state.member_repo.get_by_id(user_id)
    if not member:
        raise HTTPException(404, "Member not found")
    if member.type != MemberType.HUMAN and member.main_thread_id:
        return {"user_id": user_id, "thread_id": member.main_thread_id}
    raise HTTPException(404, "No agent thread found")
