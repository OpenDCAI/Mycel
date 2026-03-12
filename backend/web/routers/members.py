"""Members API router — DB-backed member listing."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from backend.web.core.dependencies import get_app, get_current_member_id

router = APIRouter(prefix="/api/members", tags=["members"])


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
