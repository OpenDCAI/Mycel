"""Members API router — DB-backed member listing + directory + avatars."""

import io
import logging
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from backend.web.core.dependencies import get_app, get_current_member_id
from core.agents.communication.directory_service import DirectoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/members", tags=["members"])

AVATARS_DIR = Path.home() / ".leon" / "avatars"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
AVATAR_SIZE = 256
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


@router.get("")
async def list_members(
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
) -> list[dict[str, Any]]:
    """List members visible to the authenticated user: self + contacts."""
    repo = app.state.member_repo
    contact_repo = app.state.contact_repo

    results = []

    # Own member
    me = repo.get_by_id(member_id)
    if me:
        results.append(_row_to_dict(me))

    # Contacts (agent members)
    for contact in contact_repo.list_by_owner(member_id):
        m = repo.get_by_id(contact.contact_id)
        if m:
            results.append(_row_to_dict(m))

    return results


# @@@member-directory - unified discovery endpoint backed by DirectoryService
@router.get("/directory")
async def directory(
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
    type: str | None = Query(None, description="Filter by MemberType: mycel_agent, human, openclaw_agent"),
    search: str | None = Query(None, description="Case-insensitive substring search on name or owner name"),
) -> dict[str, list[dict[str, Any]]]:
    """Browse the member directory. Returns {contacts: [...], others: [...]}.

    Same logic as the agent's logbook(directory=true) — shared DirectoryService.
    """
    svc = DirectoryService(app.state.member_repo, app.state.contact_repo)
    result = svc.browse(member_id, type_filter=type, search=search)

    def _entry_dict(e: Any) -> dict[str, Any]:
        return {
            "id": e.id,
            "name": e.name,
            "type": e.type,
            "description": e.description,
            "owner": e.owner,
            "is_contact": e.is_contact,
        }

    return {
        "contacts": [_entry_dict(e) for e in result.contacts],
        "others": [_entry_dict(e) for e in result.others],
    }


# ---------------------------------------------------------------------------
# Avatar upload + serve
# ---------------------------------------------------------------------------


def _avatar_path(member_id: str) -> Path:
    """Resolve avatar file path. member_id is validated as existing before calling."""
    # @@@path-traversal - sanitize by taking only the filename-safe part
    safe_id = Path(member_id).name
    return AVATARS_DIR / f"{safe_id}.png"


@router.put("/{member_id}/avatar")
async def upload_avatar(
    member_id: str,
    file: UploadFile,
    current_member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict[str, str]:
    """Upload/replace avatar image for a member. Resizes to 256x256 PNG."""
    repo = app.state.member_repo

    # Verify member exists
    member = repo.get_by_id(member_id)
    if not member:
        raise HTTPException(404, "Member not found")

    # Auth: can only upload for self or own agents
    if member_id != current_member_id and member.owner_id != current_member_id:
        raise HTTPException(403, "Not authorized to change this member's avatar")

    # Validate content type
    ct = file.content_type or ""
    if ct not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(400, f"Unsupported image type: {ct}. Allowed: {', '.join(ALLOWED_CONTENT_TYPES)}")

    # Read and validate size
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(400, "Empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"File too large ({len(data)} bytes). Max: {MAX_UPLOAD_BYTES}")

    # @@@pillow-re-encode - re-encode through Pillow to strip metadata, validate real image, normalize format
    try:
        from PIL import Image, ImageOps

        img = Image.open(io.BytesIO(data))
        # Auto-orient based on EXIF (fixes iPhone rotation)
        img = ImageOps.exif_transpose(img)
        # Convert to RGB (handles RGBA, palette, etc.)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        # Resize: cover-crop to square, then resize to AVATAR_SIZE
        img = ImageOps.fit(img, (AVATAR_SIZE, AVATAR_SIZE), method=Image.LANCZOS)
        # Save as PNG
        dest = _avatar_path(member_id)
        AVATARS_DIR.mkdir(parents=True, exist_ok=True)
        img.save(dest, format="PNG", optimize=True)
    except Exception as e:
        logger.error(f"Avatar processing failed for {member_id}: {e}")
        raise HTTPException(400, f"Invalid image: {e}")

    # Update DB
    repo.update(member_id, avatar=f"avatars/{member_id}.png", updated_at=time.time())
    logger.info(f"Avatar uploaded for member {member_id}")

    return {"status": "ok", "avatar": f"avatars/{member_id}.png"}


@router.get("/{member_id}/avatar")
async def get_avatar(member_id: str) -> FileResponse:
    """Serve a member's avatar image. No auth required (avatars are public)."""
    path = _avatar_path(member_id)
    if not path.exists():
        raise HTTPException(404, "No avatar")
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "no-cache"},
    )


@router.delete("/{member_id}/avatar")
async def delete_avatar(
    member_id: str,
    current_member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
) -> dict[str, str]:
    """Delete a member's avatar."""
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
    logger.info(f"Avatar deleted for member {member_id}")

    return {"status": "ok"}


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "type": row.type.value if hasattr(row.type, "value") else row.type,
        "avatar": row.avatar,
        "description": row.description,
        "config_dir": row.config_dir,
        "created_at": row.created_at,
    }
