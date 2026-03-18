"""Entity & Member endpoints — new entity-chat system."""

import io
import logging
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.web.core.dependencies import get_app, get_current_member_id
from backend.web.utils.serializers import avatar_url

logger = logging.getLogger(__name__)

AVATARS_DIR = Path.home() / ".leon" / "avatars"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
AVATAR_SIZE = 256
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}

router = APIRouter(prefix="/api/entities", tags=["entities"])

# ---------------------------------------------------------------------------
# Members (agent directory)
# ---------------------------------------------------------------------------

members_router = APIRouter(prefix="/api/members", tags=["members"])


@members_router.get("")
async def list_members(
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """List all agent members (templates). For member directory page."""
    member_repo = app.state.member_repo

    all_members = member_repo.list_all()
    result = []
    for m in all_members:
        if m.type != "mycel_agent":
            continue
        owner = member_repo.get_by_id(m.owner_id) if m.owner_id else None
        result.append({
            "id": m.id,
            "name": m.name,
            "type": m.type,
            "avatar_url": avatar_url(m.id, bool(m.avatar)),
            "description": m.description,
            "owner_name": owner.name if owner else None,
            "is_mine": m.owner_id == member_id,
            "created_at": m.created_at,
        })
    return result


def _avatar_path(member_id: str) -> Path:
    safe_id = Path(member_id).name
    return AVATARS_DIR / f"{safe_id}.png"


@members_router.put("/{member_id}/avatar")
async def upload_avatar(
    member_id: str,
    file: UploadFile,
    current_member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict[str, str]:
    """Upload/replace avatar image. Resizes to 256x256 PNG."""
    repo = app.state.member_repo
    member = repo.get_by_id(member_id)
    if not member:
        raise HTTPException(404, "Member not found")
    if member_id != current_member_id and member.owner_id != current_member_id:
        raise HTTPException(403, "Not authorized")
    ct = file.content_type or ""
    if ct not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(400, f"Unsupported image type: {ct}")
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(400, "Empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"File too large (max {MAX_UPLOAD_BYTES // 1024 // 1024}MB)")
    # @@@pillow-re-encode — strip metadata, normalize format, resize
    try:
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        img = ImageOps.fit(img, (AVATAR_SIZE, AVATAR_SIZE), method=Image.LANCZOS)
        dest = _avatar_path(member_id)
        AVATARS_DIR.mkdir(parents=True, exist_ok=True)
        img.save(dest, format="PNG", optimize=True)
    except Exception as e:
        logger.error(f"Avatar processing failed for {member_id}: {e}")
        raise HTTPException(400, f"Invalid image: {e}")
    repo.update(member_id, avatar=f"avatars/{member_id}.png", updated_at=time.time())
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
    current_member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict[str, str]:
    """Delete avatar."""
    repo = app.state.member_repo
    member = repo.get_by_id(member_id)
    if not member:
        raise HTTPException(404, "Member not found")
    if member_id != current_member_id and member.owner_id != current_member_id:
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
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """List chattable entities for discovery (New Chat picker).
    Excludes: current user's own human entity + own agent entities (those use workspace)."""
    entity_repo = app.state.entity_repo
    member_repo = app.state.member_repo

    # Find member IDs to exclude: self + own agents
    exclude_member_ids = {member_id}
    for m in member_repo.list_by_owner(member_id):
        exclude_member_ids.add(m.id)

    all_entities = entity_repo.list_all()
    return [
        {"id": e.id, "name": e.name, "type": e.type, "member_id": e.member_id,
         "avatar_url": avatar_url(e.member_id, bool(e.avatar))}
        for e in all_entities
        if e.member_id not in exclude_member_ids
    ]


@router.get("/{entity_id}/agent-thread")
async def get_agent_thread(
    entity_id: str,
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Get the thread_id for an entity's agent. Accepts human or agent entity."""
    entity = app.state.entity_repo.get_by_id(entity_id)
    if not entity:
        raise HTTPException(404, "Entity not found")
    # If this is already an agent with a thread, return directly
    if entity.type == "agent" and entity.thread_id:
        return {"entity_id": entity_id, "thread_id": entity.thread_id}
    # If this is a human entity, find the agent entity owned by the same member
    member = app.state.member_repo.get_by_id(entity.member_id)
    if member:
        # Find agent members owned by this member
        agents = app.state.member_repo.list_by_owner(member.id)
        for agent_member in agents:
            agent_entities = app.state.entity_repo.get_by_member_id(agent_member.id)
            for ae in agent_entities:
                if ae.type == "agent" and ae.thread_id:
                    return {"entity_id": ae.id, "thread_id": ae.thread_id}
    raise HTTPException(404, "No agent thread found for this entity")
